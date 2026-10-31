"""Estado do monitoramento, pronto pra tela — traduz sinais técnicos
(status HTTP, % de CPU, bytes de disco, contagem de logs de erro) em
"está tudo bem / atenção / problema" + uma explicação em português simples.

Usado tanto pelo resumo do onboarding quanto pelo dashboard (e sua
atualização ao vivo), pra que o diagrama e os indicadores contem sempre a
mesma história.

Dois níveis de alerta, de propósito:
- `warn`  ("pode virar problema"): passou do limite de atenção — nada
  quebrou ainda, mas no ritmo atual é onde problemas começam.
- `down`  ("problema agora"): passou do limite crítico ou parou de responder.

Regra de honestidade (a mesma de `resource_snapshot`): sem dado → status
`unknown` e o texto diz que não há dado. Nunca inventa número nem diz
"tudo bem" sobre algo que não foi medido.
"""
import time
from collections import deque

# (atenção, crítico) em %
THRESHOLDS = {
    "cpu": (70, 90),
    "memory": (80, 92),
    "disk": (80, 92),
    "gpu": (85, 97),
}
SLOW_RESPONSE_MS = 1000
RECENT_ERRORS_WARN = 1
RECENT_ERRORS_DOWN = 10
RECENT_ERRORS_WINDOW_MIN = 15

HISTORY_SIZE = 30
_history: dict[str, deque] = {}

STATUS_TEXT = {
    "ok": "Funcionando bem",
    "warn": "Atenção",
    "down": "Problema",
    "unknown": "Sem dados",
}
STATUS_ICON = {"ok": "✓", "warn": "!", "down": "✕", "unknown": "?"}

RESOURCE_EXPLAIN = {
    "cpu": (
        "É o \"cérebro\" do servidor: mostra o quanto ele está trabalhando agora. "
        "Picos curtos são normais; ficar alto por muito tempo deixa o sistema lento."
    ),
    "memory": (
        "Memória de trabalho (RAM): onde o sistema guarda o que está usando no momento. "
        "Se encher, tudo fica lento ou o sistema pode travar e reiniciar."
    ),
    "disk": (
        "Espaço de armazenamento: arquivos, banco de dados e registros (logs). "
        "Se encher, o sistema não consegue mais salvar nada — pedidos e cadastros falham."
    ),
    "network": (
        "Quantidade de dados entrando e saindo agora: visitas, downloads, chamadas a outros "
        "serviços. Um pico inesperado pode indicar muito acesso de uma vez — ou algo errado."
    ),
    "gpu": (
        "Placa de vídeo. Só importa se o seu sistema roda IA local ou processamento gráfico — "
        "caso contrário, pode ignorar."
    ),
}

RESOURCE_ADVICE = {
    "cpu": "Veja se algum processo travou em loop ou se o acesso subiu muito; se for acesso real, pode ser hora de um servidor maior.",
    "memory": "Reiniciar o serviço libera memória no curto prazo; se voltar a encher, pode haver um vazamento de memória no código.",
    "disk": "Apague logs e arquivos temporários antigos, ou aumente o disco antes que encha.",
    "gpu": "Confira se algum modelo de IA ficou carregado sem necessidade.",
}


def _push_history(key: str, value: float | None, store: dict | None = None) -> list[float]:
    store = _history if store is None else store
    buf = store.setdefault(key, deque(maxlen=HISTORY_SIZE))
    if value is not None:
        buf.append(float(value))
    return list(buf)


def _level(percent: float | None, key: str) -> str:
    if percent is None:
        return "unknown"
    warn, crit = THRESHOLDS[key]
    if percent >= crit:
        return "down"
    if percent >= warn:
        return "warn"
    return "ok"


def format_bytes(value: float | None) -> str:
    if value is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    return "—"


def _source_text(source: str) -> str:
    return {
        "agent": "via agente local",
        "local": "medido no host do painel",
        "unavailable": "sem dados",
        "not_collected": "não detectado",
    }.get(source, source)


def _percent_resource(key, label, icon, percent, source, detail, store=None) -> dict:
    status = _level(percent, key)
    return {
        "key": key,
        "label": label,
        "icon": icon,
        "percent": percent,
        "display": f"{percent:.0f}%" if percent is not None else "—",
        "detail": detail,
        "status": status,
        "source": source,
        "source_text": _source_text(source),
        "explain": RESOURCE_EXPLAIN[key],
        "thresholds": THRESHOLDS[key],
        "history": _push_history(key, percent, store),
    }


def build_resources(snapshot: dict, store: dict | None = None) -> list[dict]:
    resources = []

    cpu = snapshot["cpu"]["percent"]
    cores = snapshot["cpu"]["core_count"]["value"]
    resources.append(
        _percent_resource(
            "cpu", "Processador (CPU)", "⚙️", cpu["value"], cpu["source"],
            f"{cores} núcleos" if cores else "", store,
        )
    )

    used = snapshot["memory"]["used_bytes"]
    total = snapshot["memory"]["total_bytes"]["value"]
    mem_percent = (used["value"] / total * 100) if used["value"] is not None and total else None
    resources.append(
        _percent_resource(
            "memory", "Memória (RAM)", "🧠", mem_percent, used["source"],
            f"{format_bytes(used['value'])} de {format_bytes(total)}" if mem_percent is not None else "", store,
        )
    )

    # Disco: o ponto de montagem mais cheio é o que importa.
    worst = None
    for mount in snapshot["disk"]["mounts"]:
        u, t = mount["used_bytes"]["value"], mount["total_bytes"]["value"]
        if u is None or not t:
            continue
        pct = u / t * 100
        if worst is None or pct > worst[0]:
            worst = (pct, u, t, mount["mount_point"])
    resources.append(
        _percent_resource(
            "disk", "Disco", "💾",
            worst[0] if worst else None,
            snapshot["disk"]["source"],
            f"{format_bytes(worst[2] - worst[1])} livres de {format_bytes(worst[2])}" if worst else "", store,
        )
    )

    rx = snapshot["network"].get("rx_rate", {"value": None, "source": "unavailable"})
    tx = snapshot["network"].get("tx_rate", {"value": None, "source": "unavailable"})
    if rx["value"] is not None:
        total_rate = rx["value"] + (tx["value"] or 0)
        display = f"{format_bytes(total_rate)}/s"
        detail = f"↓ {format_bytes(rx['value'])}/s · ↑ {format_bytes(tx['value'])}/s"
    else:
        total_rate, display, detail = None, "—", "medindo… (precisa de duas leituras)"
    resources.append(
        {
            "key": "network",
            "label": "Tráfego de rede",
            "icon": "🌐",
            "percent": None,
            "display": display,
            "detail": detail,
            "status": "ok" if total_rate is not None else "unknown",
            "source": rx["source"],
            "source_text": _source_text(rx["source"]),
            "explain": RESOURCE_EXPLAIN["network"],
            "thresholds": None,
            "history": _push_history("network", total_rate, store),
        }
    )

    gpu = snapshot.get("gpu") or {"value": None, "source": "not_collected"}
    gpu_detail = ""
    if gpu.get("name"):
        gpu_detail = f"{gpu['name']} · {format_bytes(gpu.get('memory_used_bytes'))} de {format_bytes(gpu.get('memory_total_bytes'))}"
    gpu_res = _percent_resource("gpu", "Placa de vídeo (GPU)", "🎮", gpu["value"], gpu["source"], gpu_detail, store)
    if gpu["source"] == "not_collected":
        gpu_res["detail"] = "nenhuma GPU detectada — tudo bem se o sistema não usa"
    resources.append(gpu_res)

    return resources


def _worst(statuses: list[str]) -> str:
    for s in ("down", "warn", "ok"):
        if s in statuses:
            return s
    return "unknown"


def build_state(
    profile: dict,
    demo_app: dict,
    openobserve: dict,
    snapshot: dict,
    agent_reporting: bool,
    recent_errors: int | None,
    history: dict | None = None,
) -> dict:
    """Monta tudo o que o diagrama, os indicadores e a lista de alertas
    precisam. Nunca levanta exceção para dado faltando."""
    system_name = profile.get("system_name") or "seu sistema"
    repo_info = profile.get("repo_info") or {}
    primary_language = repo_info.get("primary_language") if repo_info.get("analyzed") else None
    resources = build_resources(snapshot, history)
    by_key = {r["key"]: r for r in resources}
    alerts: list[dict] = []

    # ---- Aplicação web -------------------------------------------------
    web_status = "ok" if demo_app.get("up") else "down"
    latency = demo_app.get("latency_ms")
    web_facts = [f"Endereço verificado: {demo_app.get('url')}"]
    if demo_app.get("up"):
        web_facts.append(f"Respondeu em {latency:.0f} ms" if latency is not None else "Respondendo")
        if latency is not None and latency >= SLOW_RESPONSE_MS:
            web_status = "warn"
            alerts.append({
                "level": "warn", "node": "webapp",
                "title": "O sistema está respondendo devagar",
                "plain": f"A última verificação levou {latency/1000:.1f} segundos. Acima de 1 segundo as pessoas já percebem a lentidão.",
                "action": "Confira o uso de CPU e memória do servidor logo abaixo — costuma ser a causa.",
            })
    else:
        alerts.append({
            "level": "down", "node": "webapp",
            "title": f"{system_name} não está respondendo",
            "plain": "Quem tentar acessar agora provavelmente vai ver uma página de erro ou nada carregar.",
            "action": "Verifique se o servidor está ligado e se o programa está rodando. Depois descreva o problema em \"Investigar\" para a IA ajudar.",
        })

    if recent_errors is not None:
        web_facts.append(f"{recent_errors} erro(s) registrados nos últimos {RECENT_ERRORS_WINDOW_MIN} min")
        if recent_errors >= RECENT_ERRORS_WARN:
            level = "down" if recent_errors >= RECENT_ERRORS_DOWN else "warn"
            if web_status == "ok" or (level == "down" and web_status == "warn"):
                web_status = level
            alerts.append({
                "level": level, "node": "webapp",
                "title": f"{recent_errors} erro(s) nos últimos {RECENT_ERRORS_WINDOW_MIN} minutos",
                "plain": "O sistema está no ar, mas algumas ações das pessoas estão falhando (ex.: finalizar uma compra).",
                "action": "Clique em \"Investigar\" e descreva o que as pessoas estão reclamando — os agentes de IA cruzam esses erros e explicam a causa.",
                "investigate": True,
            })
    else:
        web_facts.append("Contagem de erros indisponível (armazenamento de telemetria fora do ar)")

    # ---- Infra (servidor) ----------------------------------------------
    infra_resource_statuses = [by_key[k]["status"] for k in ("cpu", "memory", "disk")]
    infra_status = _worst(infra_resource_statuses)
    for key in ("cpu", "memory", "disk", "gpu"):
        r = by_key[key]
        if r["status"] not in ("warn", "down"):
            continue
        warn, crit = THRESHOLDS[key]
        if r["status"] == "down":
            title = f"{r['label']} em {r['display']} — no limite"
            plain = f"Acima de {crit}% o servidor já começa a falhar ou travar."
        else:
            title = f"{r['label']} em {r['display']} — pode virar problema"
            plain = f"Ainda funciona, mas passou do nível de atenção ({warn}%). Acima de {crit}% começam as falhas."
        alerts.append({
            "level": r["status"], "node": "infra", "resource": key,
            "title": title, "plain": plain, "action": RESOURCE_ADVICE[key],
        })

    host = snapshot.get("host_name", {}).get("value") or "não identificado"
    infra_facts = [f"Máquina: {host}"]
    for key in ("cpu", "memory", "disk"):
        r = by_key[key]
        infra_facts.append(f"{r['label']}: {r['display']}" + (f" ({r['detail']})" if r["detail"] else ""))
    if agent_reporting:
        infra_facts.append("Agente local do TracePilot enviando dados ✓")
    else:
        infra_facts.append("Agente local ainda não enviou dados — números medidos direto no host do painel")
        alerts.append({
            "level": "info", "node": "infra",
            "title": "Agente local ainda não conectado",
            "plain": "Os números acima vêm da máquina onde o painel roda. Com o agente instalado no servidor do seu sistema, eles passam a vir de lá — 24h por dia.",
            "action": "Siga o guia de instalação (cerca de 2 minutos).",
        })

    # ---- Telemetria / TracePilot ---------------------------------------
    tele_status = "ok" if openobserve.get("up") else "down"
    tele_facts = []
    if openobserve.get("up"):
        for s in openobserve.get("streams", []):
            tele_facts.append(f"{s.get('type')}: {s.get('doc_count')} registros guardados")
    else:
        alerts.append({
            "level": "warn", "node": "tracepilot",
            "title": "O TracePilot não está conseguindo guardar os dados",
            "plain": "O seu sistema não é afetado, mas enquanto isso o histórico de erros e as investigações por IA ficam sem informação nova.",
            "action": "Suba o OpenObserve (docker compose up -d) e recarregue esta página.",
        })

    # ---- Monta os nós --------------------------------------------------
    nodes = {
        "users": {
            "title": "Usuários",
            "icon": "👥",
            "status": web_status,
            "what": "As pessoas que acessam e usam o seu sistema pelo navegador ou celular.",
            "facts": [
                "Status deduzido a partir do site: se ele está fora ou lento, os usuários são os primeiros a sentir.",
                "O TracePilot ainda não mede usuários diretamente nesta versão.",
            ],
        },
        "webapp": {
            "title": "Site / Aplicação",
            "icon": "🖥️",
            "subtitle": system_name,
            "status": web_status,
            "what": "O seu sistema em si: as páginas que as pessoas veem e a lógica por trás (o \"backend\").",
            "facts": web_facts + ([f"Tecnologia principal detectada no repositório: {primary_language}"] if primary_language else []),
        },
        "database": {
            "title": "Banco de dados",
            "icon": "🗄️",
            "status": "unknown",
            "what": "Onde ficam guardadas as informações permanentes: cadastros, pedidos, produtos.",
            "facts": [
                "O TracePilot não se conecta direto ao banco nesta versão.",
                "Problemas no banco aparecem indiretamente, como erros da aplicação — e a investigação por IA consegue apontá-los.",
            ],
        },
        "infra": {
            "title": "Servidor",
            "icon": "🧱",
            "subtitle": host,
            "status": infra_status,
            "what": "A máquina (física ou na nuvem) onde tudo isso roda. Se ela sofre — pouca memória, disco cheio — tudo em cima sofre junto.",
            "facts": infra_facts,
        },
        "tracepilot": {
            "title": "TracePilot",
            "icon": "🛰️",
            "status": tele_status,
            "what": "O próprio TracePilot: recebe registros e métricas, guarda o histórico e investiga problemas com IA.",
            "facts": tele_facts or ["Armazenamento de telemetria indisponível."],
        },
    }
    for key, node in nodes.items():
        node["status_text"] = STATUS_TEXT[node["status"]]
        node["status_icon"] = STATUS_ICON[node["status"]]
        node["alert_count"] = sum(1 for a in alerts if a["node"] == key and a["level"] in ("warn", "down"))

    level_order = {"down": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: level_order[a["level"]])

    problems = [a for a in alerts if a["level"] == "down"]
    risks = [a for a in alerts if a["level"] == "warn"]
    if problems:
        overall = {
            "status": "down",
            "headline": "Há um problema afetando o sistema agora",
            "sub": problems[0]["title"],
        }
    elif risks:
        overall = {
            "status": "warn",
            "headline": "Tudo funcionando — mas há pontos de atenção",
            "sub": f"{len(risks)} item(ns) podem virar problema se nada for feito.",
        }
    else:
        overall = {
            "status": "ok",
            "headline": "Tudo funcionando normalmente",
            "sub": "Nenhum problema ou risco detectado na última verificação.",
        }

    tech = []
    if repo_info.get("analyzed"):
        langs = repo_info.get("languages") or {}
        total = sum(langs.values()) or 1
        tech = [
            {"name": name, "percent": size / total * 100}
            for name, size in sorted(langs.items(), key=lambda kv: -kv[1])[:6]
        ]

    return {
        "checked_at": time.time(),
        "overall": overall,
        "nodes": nodes,
        "resources": resources,
        "alerts": alerts,
        "problem_count": len(problems),
        "risk_count": len(risks),
        "agent_reporting": agent_reporting,
        "recent_errors": recent_errors,
        "tech": tech,
        "system_name": system_name,
    }


def example_state() -> dict:
    """Estado ilustrativo para a landing page (nunca dado real): um site
    no ar com erros recentes e disco perto do limite — mostra os dois
    níveis de alerta de uma vez."""
    def leaf(v, src="agent"):
        return {"value": v, "source": src, "label": ""}

    gb = 1024**3
    snapshot = {
        "host_name": leaf("servidor-da-loja"),
        "cpu": {"percent": leaf(38.0), "core_count": leaf(4)},
        "memory": {"used_bytes": leaf(5.1 * gb), "total_bytes": leaf(8 * gb)},
        "disk": {
            "mounts": [{"mount_point": "/", "used_bytes": leaf(68 * gb), "total_bytes": leaf(80 * gb)}],
            "source": "agent",
        },
        "network": {"rx_rate": leaf(420_000.0), "tx_rate": leaf(1_300_000.0)},
        "gpu": leaf(None, "not_collected"),
    }
    store: dict = {}
    for cpu in (22, 30, 27, 41, 35, 38):
        _push_history("cpu", cpu, store)
    state = build_state(
        profile={"system_name": "Loja da Ana"},
        demo_app={"up": True, "url": "https://loja-da-ana.com.br", "latency_ms": 180},
        openobserve={"up": True, "streams": []},
        snapshot=snapshot,
        agent_reporting=True,
        recent_errors=3,
        history=store,
    )
    return state
