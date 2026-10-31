"""Investigação aprofundada: nunca parar no "inconclusivo".

Duas partes:

1. Linha do tempo (determinística, sem LLM) numa janela larga (24 h) e em
   TODOS os serviços envolvidos, não só no de entrada:
   - origem do erro: para cada rastro com erro, segue os spans por todos os
     serviços até o span mais profundo que falhou (e a exceção dele) — num
     erro 500/502 a causa costuma estar dois ou três saltos abaixo;
   - quando começou: primeiro/último erro, pico por minuto, rotas e códigos;
   - mudanças: versão nova de um serviço que surgiu pouco antes do primeiro
     erro (deploy suspeito);
   - lentidão: duração média antes x depois do primeiro erro;
   - recursos: CPU/memória do servidor perto do primeiro erro;
   - logs de erro de todos os serviços, agrupados por mensagem.

   Roda ANTES do diagnóstico (`run_timeline`), e o digest vai para o
   diagnóstico e para o verificador.

2. Melhor palpite (LLM, `run_best_guess`), só quando o verificador não aceitou o diagnóstico:
   com a linha do tempo em mãos, o modelo é obrigado a dar a causa mais
   provável, uma confiança em % e a ação — em vez de "não temos certeza".
"""
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime

from agents.llm import LLMProvider
from agents.tools.openobserve_client import OpenObserveClient, _escape

WINDOW_HOURS = 24
DEPLOY_SUSPECT_MINUTES = 60
SAMPLE_TRACES = 6


def _fmt_ts(seconds: float) -> str:
    return datetime.fromtimestamp(seconds).strftime("%d/%m %H:%M:%S")


def _exception_from_events(raw) -> dict | None:
    try:
        events = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (json.JSONDecodeError, TypeError):
        return None
    for ev in events:
        if ev.get("name") == "exception":
            stack = ev.get("exception.stacktrace") or ""
            # Última linha do traceback costuma ser "Tipo: mensagem".
            last = next((l.strip() for l in reversed(stack.strip().splitlines()) if l.strip()), "")
            return {
                "type": ev.get("exception.type") or last.split(":")[0],
                "message": ev.get("exception.message") or (last.split(":", 1)[1].strip() if ":" in last else last),
                "where": next((l.strip() for l in reversed(stack.splitlines()) if l.strip().startswith("File ")), ""),
            }
    return None


def _search(client: OpenObserveClient, kind: str, sql: str, start_us: int, end_us: int, size: int) -> list[dict]:
    try:
        return client._search(kind, sql, start_us, end_us, size)
    except Exception:
        return []


def _error_origin(client, trace_ids, start_us, end_us) -> list[dict]:
    """Para cada rastro com erro, o span mais profundo que falhou."""
    origins = []
    for tid in trace_ids:
        spans = _search(client, "traces",
                        f"SELECT * FROM \"default\" WHERE trace_id = '{_escape(tid)}'",
                        start_us, end_us, 200)
        if not spans:
            continue
        by_id = {s.get("span_id"): s for s in spans}

        def depth(span, seen=0):
            parent = by_id.get(span.get("reference_parent_span_id"))
            return depth(parent, seen + 1) if parent and seen < 30 else seen

        failed = [s for s in spans if s.get("span_status") == "ERROR"
                  or str(s.get("http_status_code") or "").startswith("5")]
        if not failed:
            continue
        deepest = max(failed, key=lambda s: (depth(s), s.get("start_time") or 0))
        chain = []
        node = deepest
        while node is not None and len(chain) < 10:
            chain.append(f"{node.get('service_name')}:{node.get('operation_name')}"
                         + (f" ({node.get('http_status_code')})" if node.get("http_status_code") else ""))
            node = by_id.get(node.get("reference_parent_span_id"))
        origins.append({
            "trace_id": tid,
            "service": deepest.get("service_name"),
            "operation": deepest.get("operation_name"),
            "exception": _exception_from_events(deepest.get("events")),
            "chain": list(reversed(chain)),
            "version": deepest.get("service_service_version"),
        })
    return origins


def build_timeline(client: OpenObserveClient, services: list[str], end_us: int | None = None) -> dict:
    end_us = end_us or int(time.time() * 1_000_000)
    start_us = end_us - WINDOW_HOURS * 3600 * 1_000_000
    in_list = ", ".join(f"'{_escape(s)}'" for s in services)
    entry = services[0]

    # 1. Erros do serviço de entrada, em ordem cronológica.
    errors = _search(client, "traces",
                     "SELECT _timestamp, trace_id, http_route, http_target, http_status_code, operation_name, "
                     "service_service_version, duration FROM \"default\" "
                     f"WHERE service_name = '{_escape(entry)}' AND span_kind = '2' "
                     "AND (span_status = 'ERROR' OR http_status_code >= '500') ORDER BY _timestamp ASC",
                     start_us, end_us, 2000)
    events: list[dict] = []
    facts: dict = {"services": services, "window_hours": WINDOW_HOURS, "error_count": len(errors)}
    if errors:
        first = errors[0]["_timestamp"] / 1e6
        last = errors[-1]["_timestamp"] / 1e6
        per_minute = Counter(int(e["_timestamp"] / 6e7) for e in errors)
        peak_min, peak_n = per_minute.most_common(1)[0]
        routes = Counter(e.get("http_route") or e.get("http_target") or e.get("operation_name") for e in errors)
        codes = Counter(str(e.get("http_status_code")) for e in errors)
        facts.update({
            "first_error": first, "last_error": last,
            "peak": {"at": peak_min * 60, "count": peak_n},
            "routes": routes.most_common(5), "status_codes": codes.most_common(5),
        })
        events.append({"t": first, "kind": "error", "text": f"Primeiro erro em {entry}: {routes.most_common(1)[0][0]} ({errors[0].get('http_status_code')})"})
        events.append({"t": peak_min * 60, "kind": "error", "text": f"Pico: {peak_n} erros no mesmo minuto"})
        if last - first > 60:
            events.append({"t": last, "kind": "error", "text": f"Último erro registrado ({len(errors)} no total)"})

        # 2. Origem: segue os rastros mais recentes até o span mais profundo que falhou.
        recent_ids = list(dict.fromkeys(e["trace_id"] for e in reversed(errors) if e.get("trace_id")))[:SAMPLE_TRACES]
        origins = _error_origin(client, recent_ids, start_us, end_us)
        facts["origins"] = origins
        if origins:
            top = Counter((o["service"], o["operation"], (o["exception"] or {}).get("type")) for o in origins).most_common(1)[0][0]
            sample = next(o for o in origins if (o["service"], o["operation"], (o["exception"] or {}).get("type")) == top)
            exc = sample["exception"]
            facts["origin"] = sample
            # Horário do próprio rastro analisado (não do primeiro erro da
            # janela, que pode ser de outro incidente mais antigo).
            origin_t = next((e["_timestamp"] / 1e6 for e in errors if e.get("trace_id") == sample["trace_id"]), first)
            events.append({"t": origin_t, "kind": "origin",
                           "text": f"Origem: {sample['service']} → {sample['operation']}"
                                   + (f" lançou {exc['type']}: {exc['message'][:120]}" if exc else " falhou")})

        # 3. Latência antes x depois do primeiro erro (rota mais afetada).
        top_route = routes.most_common(1)[0][0]
        before = _search(client, "traces",
                         f"SELECT AVG(duration) AS avg_d, COUNT(*) AS n FROM \"default\" WHERE service_name = '{_escape(entry)}' "
                         f"AND span_kind = '2' AND http_route = '{_escape(str(top_route))}'",
                         int((first - 1800) * 1e6), int(first * 1e6), 1)
        after = _search(client, "traces",
                        f"SELECT AVG(duration) AS avg_d, COUNT(*) AS n FROM \"default\" WHERE service_name = '{_escape(entry)}' "
                        f"AND span_kind = '2' AND http_route = '{_escape(str(top_route))}'",
                        int(first * 1e6), end_us, 1)
        try:
            b_ms = (before[0]["avg_d"] or 0) / 1000
            a_ms = (after[0]["avg_d"] or 0) / 1000
            if before[0]["n"] and after[0]["n"]:
                facts["latency"] = {"route": top_route, "before_ms": round(b_ms), "after_ms": round(a_ms)}
                if a_ms > b_ms * 2 and a_ms - b_ms > 200:
                    events.append({"t": first, "kind": "latency",
                                   "text": f"{top_route} ficou mais lenta: {b_ms:.0f} ms → {a_ms:.0f} ms em média"})
        except (IndexError, KeyError, TypeError):
            pass

        # 4. Recursos do servidor perto do primeiro erro (TracePilot Collector).
        cpu = _search(client, "metrics",
                      "SELECT MAX(value) AS peak FROM \"system_cpu_usage_percent\"",
                      int((first - 300) * 1e6), int((first + 300) * 1e6), 1)
        try:
            peak = cpu[0]["peak"]
            if peak is not None:
                facts["cpu_peak_near_first_error"] = round(peak)
                if peak >= 85:
                    events.append({"t": first, "kind": "resource", "text": f"CPU do servidor chegou a {peak:.0f}% perto do primeiro erro"})
        except (IndexError, KeyError, TypeError):
            pass

    # 5. Deploys: versão de cada serviço e quando apareceu pela primeira vez.
    versions = _search(client, "traces",
                       "SELECT service_name, service_service_version AS v, MIN(_timestamp) AS first_seen, COUNT(*) AS n "
                       f"FROM \"default\" WHERE service_name IN ({in_list}) GROUP BY service_name, service_service_version",
                       start_us, end_us, 50)
    by_service = defaultdict(list)
    for v in versions:
        if v.get("v"):
            by_service[v["service_name"]].append(v)
    facts["versions"] = {s: sorted([(x["v"], x["first_seen"] / 1e6) for x in vs], key=lambda t: t[1]) for s, vs in by_service.items()}
    # (horário, rota, versão) de cada erro do serviço de entrada — a versão
    # vem do próprio span (resource service.version).
    error_pts = [(e["_timestamp"] / 1e6,
                  e.get("http_route") or e.get("http_target") or e.get("operation_name"),
                  e.get("service_service_version"))
                 for e in errors]
    facts["suspect_deploys"] = []
    for service, vs in facts["versions"].items():
        for i, (ver, seen) in enumerate(vs):
            if i == 0:
                continue
            prev = vs[i - 1][0]
            text = f"Deploy: {service} {prev} → {ver}"
            # Suspeito = numa rota, a versão nova erra bem mais que a anterior
            # nos 30 min antes do deploy. Comparar por versão (e não só por
            # horário) não se confunde com erro isolado ou outro incidente.
            win = DEPLOY_SUSPECT_MINUTES * 30
            new_by_route = Counter(r for t, r, v in error_pts if v == ver and seen <= t < seen + win)
            old_by_route = Counter(r for t, r, v in error_pts if v == prev and seen - win <= t < seen)
            worse = [(r, n, old_by_route.get(r, 0)) for r, n in new_by_route.items()
                     if n >= 3 and n > 2 * old_by_route.get(r, 0)]
            if service == entry and worse:
                route, n, old = max(worse, key=lambda w: w[1])
                text += f" — com a versão nova, {route} passou a falhar ({n} erros; {old} na versão anterior)"
                facts["suspect_deploys"].append({"service": service, "from": prev, "to": ver,
                                                 "at": seen, "route": route, "after": n, "before": old})
            events.append({"t": seen, "kind": "deploy", "text": text})

    # 6. Logs de erro de todos os serviços, agrupados por mensagem.
    logs = _search(client, "logs",
                   "SELECT _timestamp, service_name, severity, body, exception_type, exception_message FROM \"default\" "
                   f"WHERE service_name IN ({in_list}) AND severity IN ('ERROR', 'CRITICAL', 'FATAL', 'WARNING', 'WARN') "
                   "ORDER BY _timestamp ASC",
                   start_us, end_us, 500)
    groups: dict[tuple, dict] = {}
    for rec in logs:
        # Tokens com dígitos (IDs de pedido, hashes, números) viram "#", para
        # "ORD-59f3… falhou" e "ORD-09b8… falhou" contarem como a mesma mensagem.
        key = (rec.get("service_name"), re.sub(r"\S*\d\S*", "#", str(rec.get("body") or ""))[:80])
        g = groups.setdefault(key, {"service": key[0], "message": str(rec.get("body") or "")[:160],
                                    "exception": rec.get("exception_type"), "count": 0,
                                    "first": rec["_timestamp"] / 1e6, "severity": rec.get("severity")})
        g["count"] += 1
    top_logs = sorted(groups.values(), key=lambda g: -g["count"])[:6]
    facts["log_groups"] = top_logs
    for g in top_logs[:3]:
        events.append({"t": g["first"], "kind": "log",
                       "text": f"{g['service']} registrou {g['count']}× \"{g['message'][:90]}\""})

    events.sort(key=lambda e: e["t"])
    for e in events:
        e["when"] = _fmt_ts(e["t"])
    return {"events": events, "facts": facts}


def digest(timeline: dict) -> str:
    """Texto compacto da linha do tempo para o LLM."""
    f = timeline["facts"]
    lines = [f"Janela analisada: últimas {f['window_hours']} h; serviços: {', '.join(f['services'])}."]
    if not f.get("error_count"):
        lines.append("Nenhum erro 5xx registrado no serviço de entrada nessa janela.")
    else:
        lines.append(f"Erros no serviço de entrada: {f['error_count']} (de {_fmt_ts(f['first_error'])} a {_fmt_ts(f['last_error'])}).")
        lines.append("Rotas: " + ", ".join(f"{r} ({n})" for r, n in f["routes"]) + "; códigos: " + ", ".join(f"{c} ({n})" for c, n in f["status_codes"]))
    o = f.get("origin")
    if o:
        exc = o.get("exception")
        lines.append("Cadeia do erro (de fora para dentro): " + " → ".join(o["chain"]))
        lines.append(f"Span mais profundo que falhou: {o['service']}:{o['operation']}"
                     + (f", exceção {exc['type']}: {exc['message']}" + (f" ({exc['where']})" if exc.get("where") else "") if exc else ""))
        same = sum(1 for x in f.get("origins", []) if x["service"] == o["service"] and x["operation"] == o["operation"])
        lines.append(f"Mesma origem em {same} de {len(f.get('origins', []))} rastros com erro analisados.")
    # Conclusão explícita junto do número: modelos pequenos leem "53 x 51 ms"
    # ou "CPU 19%" como "pico" se o texto não disser que está normal.
    if f.get("latency"):
        l = f["latency"]
        slower = l["after_ms"] > l["before_ms"] * 2 and l["after_ms"] - l["before_ms"] > 200
        lines.append(f"Latência de {l['route']}: {l['before_ms']} ms antes x {l['after_ms']} ms depois do primeiro erro"
                     + (" — FICOU MAIS LENTA." if slower else " — sem mudança relevante (não é lentidão)."))
    if f.get("cpu_peak_near_first_error") is not None:
        cpu = f["cpu_peak_near_first_error"]
        lines.append(f"Pico de CPU do servidor perto do primeiro erro: {cpu}%"
                     + (" — ALTO." if cpu >= 85 else " — normal (não é falta de CPU)."))
    for service, vs in f.get("versions", {}).items():
        if len(vs) > 1:
            lines.append(f"Versões de {service} na janela: " + ", ".join(f"{v} (desde {_fmt_ts(t)})" for v, t in vs))
    for d in f.get("suspect_deploys", []):
        lines.append(f"DEPLOY SUSPEITO: {d['service']} {d['from']} → {d['to']} em {_fmt_ts(d['at'])}; "
                     f"com a versão nova, a rota {d['route']} passou a falhar ({d['after']} erros; {d['before']} na versão anterior nos 30 min antes).")
    for g in f.get("log_groups", [])[:5]:
        lines.append(f"Log {g['severity']} em {g['service']} ({g['count']}×, desde {_fmt_ts(g['first'])}): {g['message']}")
    lines.append("Linha do tempo:")
    lines += [f"- {e['when']} [{e['kind']}] {e['text']}" for e in timeline["events"][:15]]
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Você é um engenheiro sênior de confiabilidade investigando um erro 500 em produção. "
    "A primeira análise não foi conclusiva. Com a linha do tempo e a cadeia de spans abaixo, "
    "você DEVE dar a causa mais provável — nunca responda que não é possível saber. "
    "Baseie-se só nos dados fornecidos, prefira a origem mais profunda da cadeia de spans "
    "e use a temporalidade (o que mudou pouco antes do primeiro erro). Seja honesto na confiança."
)

PROMPT_TEMPLATE = """Relato: {error_report}

Hipóteses iniciais: {hypotheses}

Por que a verificação não aceitou: {verification_notes}

Evidência aprofundada:
{digest}

Responda EXATAMENTE neste formato:
PALPITE: <causa mais provável, 1 a 2 frases, citando o serviço/operação de origem>
CONFIANCA: <número de 0 a 100>
PORQUE: <1 a 2 frases ligando o palpite aos fatos acima (cadeia de spans, horário, deploy, logs)>
ACAO: <ação concreta para corrigir>"""

_FIELD_RE = re.compile(r"^(PALPITE|CONFIANCA|CONFIANÇA|PORQUE|ACAO|AÇÃO)\s*:\s*(.+)$", re.IGNORECASE)


def _parse_guess(text: str) -> dict:
    out: dict = {}
    for line in text.splitlines():
        m = _FIELD_RE.match(line.strip())
        if m:
            key = m.group(1).upper().replace("Ç", "C").replace("Ã", "A")
            out.setdefault(key, m.group(2).strip())
    try:
        conf = int(re.search(r"\d+", out.get("CONFIANCA", "")).group(0))
    except (AttributeError, ValueError):
        conf = None
    return {
        "best_guess": out.get("PALPITE") or text.strip()[:400],
        "best_guess_confidence": max(0, min(100, conf)) if conf is not None else None,
        "best_guess_reason": out.get("PORQUE", ""),
        "best_guess_action": out.get("ACAO", ""),
    }


def run_timeline(state: dict, client: OpenObserveClient) -> dict:
    """Etapa determinística — roda ANTES do diagnóstico, para ele (e o
    verificador) já enxergarem a origem do erro entre serviços. Sem isso o
    diagnóstico via só o serviço de entrada e chutava a dependência mais
    próxima (ex.: o proxy) em vez da origem real três saltos abaixo."""
    services = [state.get("service")] + list(state.get("related_services") or [])
    services = list(dict.fromkeys(s for s in services if s))
    if not services:
        return {**state, "timeline": [], "deep_dive_digest": "(serviço não informado)"}
    try:
        timeline = build_timeline(client, services, state.get("end_time"))
    except Exception as exc:  # noqa: BLE001 — a investigação segue sem a linha do tempo
        return {**state, "timeline": [], "deep_dive_error": str(exc), "deep_dive_digest": "(indisponível)"}
    result = {**state, "timeline": timeline["events"], "timeline_facts": timeline["facts"],
              "deep_dive_digest": digest(timeline)}
    if timeline["facts"].get("origin"):
        result["error_origin"] = timeline["facts"]["origin"]
    return result


def run_best_guess(state: dict, llm: LLMProvider) -> dict:
    """Só quando o verificador não aceitou: obriga um melhor palpite com
    confiança, em vez de terminar em "não temos certeza"."""
    if state.get("verified"):
        return state
    raw = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            error_report=state.get("error_report", ""),
            hypotheses=state.get("hypotheses", "(nenhuma)"),
            verification_notes=state.get("verification_notes", "(não executada)"),
            digest=state.get("deep_dive_digest", "(indisponível)"),
        ),
        system=SYSTEM_PROMPT,
    )
    return {**state, **_parse_guess(raw)}
