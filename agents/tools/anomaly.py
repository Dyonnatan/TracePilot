"""Detecção de anomalias SEM erro — lentidão, consumo de recursos, padrões
de chamada e volume de logs —, comparando uma janela recente com a base
anterior. Cobre o que a contagem de erros não vê: índice inválido, I/O
síncrono, N+1, retries, CPU saturada num contêiner, vazamento de memória,
log de debug esquecido em produção.

Usado pelo painel (recente = últimos 5 min x base = 60 min antes) e pela
investigação aprofundada (recente = janela do incidente). Determinístico e
explicável: cada sinal vira uma frase com o antes e o depois.

Mediana em vez de média na base: um cenário anterior (um lock de 2 s, por
exemplo) não "suja" a referência de normalidade.
"""
import time

from agents.tools.openobserve_client import OpenObserveClient, _escape

# Limites (conservadores para não gritar à toa)
ROUTE_RATIO, ROUTE_MIN_DELTA_MS, MIN_SAMPLES = 2.0, 150, 5
OP_RATIO, OP_MIN_DELTA_MS = 3.0, 100
CALLS_RATIO, CALLS_MIN = 2.5, 4
CPU_RATIO, CPU_MIN_PCT = 3.0, 35          # % de UM núcleo (docker_stats)
MEM_DELTA_PCT = 10                         # pontos percentuais do limite do contêiner
LOG_RATIO, LOG_MIN_PER_MIN = 4.0, 60
SQL_RATIO, SQL_MIN_DELTA_MS = 3.0, 10       # por consulta: um índice inválido vai de 2 ms a 47 ms

_cache: dict = {}


def _search(client, kind, sql, start_us, end_us, size=200) -> list[dict]:
    try:
        return client._search(kind, sql, start_us, end_us, size)
    except Exception:
        return []


def _windows(recent_min: int, base_min: int, end_us: int | None):
    end_us = end_us or int(time.time() * 1_000_000)
    mid = end_us - recent_min * 60 * 1_000_000
    start = mid - base_min * 60 * 1_000_000
    return (start, mid), (mid, end_us)


def _container_label(name: str) -> str:
    # tracepilot-demo-payment-service-1 → payment-service
    for prefix in ("tracepilot-demo-",):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.rsplit("-", 1)[0] if name.rsplit("-", 1)[-1].isdigit() else name


def detect(client: OpenObserveClient, services: list[str], recent_min: int = 5,
           base_min: int = 60, end_us: int | None = None) -> dict:
    """Sinais de anomalia, cada um com `kind`, `level`, `node`, `title`,
    `detail` e números de antes/depois."""
    services = [s for s in services if s]
    if not services:
        return {"signals": [], "db": None}
    (b0, b1), (r0, r1) = _windows(recent_min, base_min, end_us)
    in_list = ", ".join(f"'{_escape(s)}'" for s in services)
    entry = services[0]
    signals: list[dict] = []

    # 1. Rotas do serviço de entrada mais lentas.
    q = ("SELECT http_route, approx_median(duration) AS med, COUNT(*) AS n FROM \"default\" "
         f"WHERE service_name = '{_escape(entry)}' AND span_kind = '2' AND http_route IS NOT NULL GROUP BY http_route")
    base = {h["http_route"]: h for h in _search(client, "traces", q, b0, b1)}
    for h in _search(client, "traces", q, r0, r1):
        b = base.get(h["http_route"])
        if not b or h["n"] < MIN_SAMPLES or b["n"] < MIN_SAMPLES:
            continue
        before, after = b["med"] / 1000, h["med"] / 1000
        if after >= before * ROUTE_RATIO and after - before >= ROUTE_MIN_DELTA_MS:
            ratio = after / max(before, 1)
            signals.append({
                "kind": "route_latency", "level": "down" if ratio >= 5 else "warn", "node": "webapp",
                "route": h["http_route"], "before": round(before), "after": round(after),
                "title": f"{h['http_route']} {ratio:.0f}× mais lenta ({before:.0f} ms → {after:.0f} ms)",
                "detail": "mediana do tempo de resposta, sem erro",
            })

    slow_routes = {x["route"] for x in signals if x["kind"] == "route_latency"}

    # 2. Operações internas (todos os serviços): mais lentas e mais chamadas por requisição.
    q = ("SELECT service_name, operation_name, approx_median(duration) AS med, COUNT(*) AS n, "
         f"COUNT(DISTINCT trace_id) AS traces FROM \"default\" WHERE service_name IN ({in_list}) "
         "GROUP BY service_name, operation_name")
    base = {(h["service_name"], h["operation_name"]): h for h in _search(client, "traces", q, b0, b1, 500)}
    for h in _search(client, "traces", q, r0, r1, 500):
        key = (h["service_name"], h["operation_name"])
        b = base.get(key)
        if not b or h["n"] < MIN_SAMPLES or b["n"] < MIN_SAMPLES:
            continue
        op = f"{key[0]}:{key[1]}"
        before, after = b["med"] / 1000, h["med"] / 1000
        # O span de servidor "POST /checkout" do serviço de entrada é a
        # própria rota /checkout, já apontada acima: não repetir.
        same_as_route = key[0] == entry and any(key[1].endswith(" " + r) for r in slow_routes)
        if not same_as_route and after >= before * OP_RATIO and after - before >= OP_MIN_DELTA_MS:
            signals.append({
                "kind": "op_latency", "level": "warn", "node": "database" if key[1] in ("SELECT", "INSERT", "UPDATE", "DELETE") else "webapp",
                "operation": op, "before": round(before), "after": round(after),
                "title": f"{op} {after / max(before, 0.001):.0f}× mais lenta ({before:.0f} ms → {after:.0f} ms)",
                "detail": "operação interna (span), mediana",
            })
        per_before = b["n"] / max(b["traces"], 1)
        per_after = h["n"] / max(h["traces"], 1)
        if per_after >= per_before * CALLS_RATIO and per_after >= CALLS_MIN:
            is_db = key[1] in ("SELECT", "INSERT", "UPDATE", "DELETE")
            signals.append({
                "kind": "n_plus_one" if is_db else "repeated_calls", "level": "warn",
                "node": "database" if is_db else "webapp", "operation": op,
                "before": round(per_before, 1), "after": round(per_after, 1),
                "title": (f"Consultas ao banco por requisição: {per_before:.0f} → {per_after:.0f} ({op})" if is_db
                          else f"Chamadas repetidas por requisição: {per_before:.1f} → {per_after:.1f} ({op})"),
                "detail": "possível N+1 (uma consulta por item)" if is_db else "possível tempestade de retries",
            })

    # 2b. Cada consulta SQL separada (pelo texto): misturar todas numa mediana
    # só esconde a consulta que piorou (as rápidas dominam).
    q = ("SELECT service_name, substr(db_statement, 1, 160) AS st, approx_median(duration) AS med, COUNT(*) AS n "
         f"FROM \"default\" WHERE service_name IN ({in_list}) AND db_system IS NOT NULL GROUP BY service_name, st")
    base = {(h["service_name"], h["st"]): h for h in _search(client, "traces", q, b0, b1, 500)}
    for h in _search(client, "traces", q, r0, r1, 500):
        b = base.get((h["service_name"], h["st"]))
        if not b or h["n"] < MIN_SAMPLES or b["n"] < MIN_SAMPLES:
            continue
        before, after = b["med"] / 1000, h["med"] / 1000
        if after >= before * SQL_RATIO and after - before >= SQL_MIN_DELTA_MS:
            stmt = " ".join((h["st"] or "").split())[:70]
            signals.append({
                "kind": "sql_latency", "level": "warn", "node": "database", "statement": stmt,
                "before": round(before, 1), "after": round(after, 1),
                "title": f"Consulta ao banco {after / max(before, 0.001):.0f}× mais lenta ({before:.1f} ms → {after:.1f} ms)",
                "detail": f"\"{stmt}…\" — possível índice faltando ou inválido (leitura da tabela inteira)",
            })

    # 3. Contêineres: CPU e memória.
    q = 'SELECT container_name, AVG(value) AS v FROM "{s}" GROUP BY container_name'
    cpu_b = {h["container_name"]: h["v"] for h in _search(client, "metrics", q.format(s="container_cpu_utilization"), b0, b1)}
    for h in _search(client, "metrics", q.format(s="container_cpu_utilization"), r0, r1):
        before, after = cpu_b.get(h["container_name"]), h["v"]
        if before is None or after is None:
            continue
        if after >= CPU_MIN_PCT and after >= max(before, 1) * CPU_RATIO:
            name = _container_label(h["container_name"])
            signals.append({
                "kind": "container_cpu", "level": "down" if after >= 80 else "warn", "node": "infra",
                "container": name, "before": round(before), "after": round(after),
                "title": f"CPU do contêiner {name}: {before:.0f}% → {after:.0f}% de um núcleo",
                "detail": "a máquina pode estar folgada; o limite é do contêiner",
            })
    mem_b = {h["container_name"]: h["v"] for h in _search(client, "metrics", q.format(s="container_memory_percent"), b0, b1)}
    for h in _search(client, "metrics", q.format(s="container_memory_percent"), r0, r1):
        before, after = mem_b.get(h["container_name"]), h["v"]
        if before is None or after is None:
            continue
        if after - before >= MEM_DELTA_PCT:
            name = _container_label(h["container_name"])
            signals.append({
                "kind": "container_memory", "level": "down" if after >= 85 else "warn", "node": "infra",
                "container": name, "before": round(before), "after": round(after),
                "title": f"Memória do contêiner {name} subindo: {before:.0f}% → {after:.0f}% do limite",
                "detail": "crescimento contínuo pode indicar vazamento de memória",
            })

    # 4. Volume de logs por serviço (por minuto).
    q = f'SELECT service_name, COUNT(*) AS n FROM "default" WHERE service_name IN ({in_list}) GROUP BY service_name'
    log_b = {h["service_name"]: h["n"] / base_min for h in _search(client, "logs", q, b0, b1)}
    for h in _search(client, "logs", q, r0, r1):
        before, after = log_b.get(h["service_name"], 0), h["n"] / recent_min
        if after >= LOG_MIN_PER_MIN and after >= max(before, 1) * LOG_RATIO:
            signals.append({
                "kind": "log_volume", "level": "warn", "node": "webapp", "service": h["service_name"],
                "before": round(before), "after": round(after),
                "title": f"Volume de logs de {h['service_name']}: {before:.0f} → {after:.0f} por minuto",
                "detail": "log em excesso deixa o sistema mais lento e encarece a ingestão",
            })

    # 5. Banco de dados: erros e tempo dos spans de banco (db_system preenchido).
    q = ("SELECT approx_median(duration) AS med, COUNT(*) AS n, "
         "SUM(CASE WHEN span_status = 'ERROR' THEN 1 ELSE 0 END) AS errors FROM \"default\" "
         f"WHERE service_name IN ({in_list}) AND db_system IS NOT NULL")
    db_b = (_search(client, "traces", q, b0, b1, 1) or [{}])[0]
    db_r = (_search(client, "traces", q, r0, r1, 1) or [{}])[0]
    db = None
    if db_r.get("n"):
        db = {
            "queries": db_r["n"], "errors": int(db_r.get("errors") or 0),
            "median_ms": round((db_r.get("med") or 0) / 1000, 1),
            "base_median_ms": round((db_b.get("med") or 0) / 1000, 1) if db_b.get("n") else None,
        }
        if db["errors"]:
            signals.append({
                "kind": "db_errors", "level": "down", "node": "database",
                "title": f"Banco de dados com {db['errors']} consultas falhando",
                "detail": f"{db['queries']} consultas nos últimos {recent_min} min",
            })

    order = {"down": 0, "warn": 1}
    signals.sort(key=lambda s: order.get(s["level"], 2))
    return {"signals": signals, "db": db, "window": {"recent_min": recent_min, "base_min": base_min}}


def detect_cached(client: OpenObserveClient, services: list[str], ttl: int = 20) -> dict:
    """Para o painel (que atualiza a cada 10 s): reaproveita o resultado por
    `ttl` segundos — são ~10 consultas agregadas por rodada."""
    key = tuple(services)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    result = detect(client, services)
    _cache[key] = (time.time(), result)
    return result
