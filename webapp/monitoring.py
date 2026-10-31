"""Estado do monitoramento, pronto pra tela: traduz sinais técnicos em
status (normal / atenção / problema / sem dados) e textos curtos.

Usado pelo resumo do onboarding, pelo painel (e sua atualização ao vivo) e,
com dados ilustrativos, pela landing page.

Dois níveis de alerta:
- `warn`: passou do limite de atenção. Nada quebrou, mas é onde começa.
- `down`: passou do limite crítico ou parou de responder.

Sem dado → `unknown`. Nunca inventa número nem diz "normal" sobre algo
que não foi medido.
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

STATUS_TEXT = {"ok": "Normal", "warn": "Atenção", "down": "Problema", "unknown": "Sem dados"}
STATUS_ICON = {"ok": "✓", "warn": "!", "down": "✕", "unknown": "?"}

RESOURCE_LABELS = {
    "cpu": ("CPU", "Processador"),
    "memory": ("RAM", "Memória"),
    "disk": ("Disco", "Disco"),
    "network": ("Rede", "Tráfego de rede"),
    "gpu": ("GPU", "Placa de vídeo"),
}

RESOURCE_EXPLAIN = {
    "cpu": "Quanto o processador está trabalhando. Alto por muito tempo deixa tudo lento.",
    "memory": "Memória em uso agora. Se encher, o sistema trava ou reinicia.",
    "disk": "Espaço para arquivos, banco e logs. Cheio, nada mais é salvo.",
    "network": "Dados entrando e saindo por segundo.",
    "gpu": "Só importa se o sistema roda IA ou gráficos.",
}

RESOURCE_ADVICE = {
    "cpu": "Veja se há acesso fora do normal ou um processo travado.",
    "memory": "Reinicie o serviço. Se voltar a encher, pode ser vazamento de memória.",
    "disk": "Apague logs e arquivos antigos ou aumente o disco.",
    "gpu": "Verifique se algum modelo de IA ficou carregado à toa.",
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


SOURCE_TEXT = {
    "agent": "agente",
    "local": "medido pelo painel",
    "unavailable": "sem dados",
    "not_collected": "não detectado",
}


def _resource(key, percent, source, detail, store=None, display=None, status=None) -> dict:
    short, label = RESOURCE_LABELS[key]
    return {
        "key": key,
        "short": short,
        "label": label,
        "percent": percent,
        "display": display or (f"{percent:.0f}%" if percent is not None else "—"),
        "detail": detail,
        "status": status or _level(percent, key),
        "source": source,
        "source_text": SOURCE_TEXT.get(source, source),
        "explain": RESOURCE_EXPLAIN[key],
        "thresholds": THRESHOLDS.get(key),
        "history": _push_history(key, percent if key != "network" else None, store),
    }


def build_resources(snapshot: dict, store: dict | None = None) -> list[dict]:
    cpu = snapshot["cpu"]["percent"]
    cores = snapshot["cpu"]["core_count"]["value"]
    resources = [_resource("cpu", cpu["value"], cpu["source"], f"{cores} núcleos" if cores else "", store)]

    used = snapshot["memory"]["used_bytes"]
    total = snapshot["memory"]["total_bytes"]["value"]
    mem_percent = (used["value"] / total * 100) if used["value"] is not None and total else None
    resources.append(_resource(
        "memory", mem_percent, used["source"],
        f"{format_bytes(used['value'])} de {format_bytes(total)}" if mem_percent is not None else "", store,
    ))

    # Disco: o ponto de montagem mais cheio é o que importa.
    worst = None
    for mount in snapshot["disk"]["mounts"]:
        u, t = mount["used_bytes"]["value"], mount["total_bytes"]["value"]
        if u is None or not t:
            continue
        pct = u / t * 100
        if worst is None or pct > worst[0]:
            worst = (pct, u, t)
    resources.append(_resource(
        "disk", worst[0] if worst else None, snapshot["disk"]["source"],
        f"{format_bytes(worst[2] - worst[1])} livres" if worst else "", store,
    ))

    rx = snapshot["network"].get("rx_rate", {"value": None, "source": "unavailable"})
    tx = snapshot["network"].get("tx_rate", {"value": None, "source": "unavailable"})
    if rx["value"] is not None:
        rate = rx["value"] + (tx["value"] or 0)
        net = _resource(
            "network", None, rx["source"],
            f"↓ {format_bytes(rx['value'])}/s  ↑ {format_bytes(tx['value'])}/s",
            store, display=f"{format_bytes(rate)}/s", status="ok",
        )
    else:
        rate = None
        net = _resource("network", None, rx["source"], "medindo…", store)
    net["history"] = _push_history("network", rate, store)
    resources.append(net)

    gpu = snapshot.get("gpu") or {"value": None, "source": "not_collected"}
    gpu_detail = gpu.get("name", "").replace("NVIDIA GeForce ", "") if gpu.get("name") else "nenhuma"
    resources.append(_resource("gpu", gpu["value"], gpu["source"], gpu_detail, store))
    return resources


def _worst(statuses: list[str]) -> str:
    for s in ("down", "warn", "ok"):
        if s in statuses:
            return s
    return "unknown"


def _connection(openobserve_up: bool, agent_reporting: bool, sources: dict | None) -> dict:
    """Como o TracePilot está recebendo dados do sistema monitorado."""
    channels = []
    if agent_reporting:
        channels.append("agente")
    if sources and sources.get("direct_api"):
        channels.append("API")
    if sources and (sources.get("logs") or sources.get("traces")) and not sources.get("direct_api"):
        channels.append("OTel")
    receiving = bool(sources and (sources.get("logs") or sources.get("traces")))

    if not openobserve_up:
        return {"status": "down", "text": "Fora do ar", "via": "", "channels": []}
    if not channels:
        return {"status": "warn", "text": "Sem dados", "via": "aguardando dados", "channels": []}
    via = " + ".join(channels)
    if receiving or agent_reporting:
        return {"status": "ok", "text": "Conectado", "via": via, "channels": channels}
    return {"status": "warn", "text": "Parcial", "via": via, "channels": channels}


def build_state(
    profile: dict,
    demo_app: dict,
    openobserve: dict,
    snapshot: dict,
    agent_reporting: bool,
    recent_errors: int | None,
    sources: dict | None = None,
    history: dict | None = None,
) -> dict:
    """Monta tudo o que o diagrama, os indicadores e os alertas precisam.
    Nunca levanta exceção por dado faltando."""
    system_name = profile.get("system_name") or "Seu sistema"
    repo_info = profile.get("repo_info") or {}
    primary_language = repo_info.get("primary_language") if repo_info.get("analyzed") else None
    resources = build_resources(snapshot, history)
    by_key = {r["key"]: r for r in resources}
    alerts: list[dict] = []
    host = snapshot.get("host_name", {}).get("value") or "não identificado"

    # ---- Site / app ----------------------------------------------------
    web_status = "ok" if demo_app.get("up") else "down"
    latency = demo_app.get("latency_ms")
    web_facts = [("Endereço", demo_app.get("url") or "—")]
    if demo_app.get("up"):
        web_facts.append(("Resposta", f"{latency:.0f} ms" if latency is not None else "ok"))
        if latency is not None and latency >= SLOW_RESPONSE_MS:
            web_status = "warn"
            alerts.append({
                "level": "warn", "node": "webapp",
                "title": f"Resposta lenta: {latency / 1000:.1f} s",
                "action": "Veja CPU e memória do servidor.",
            })
    else:
        web_facts.append(("Resposta", "não respondeu"))
        alerts.append({
            "level": "down", "node": "webapp",
            "title": f"{system_name} não responde",
            "action": "Verifique se o servidor e o programa estão ligados.",
        })

    if recent_errors is not None:
        web_facts.append((f"Erros ({RECENT_ERRORS_WINDOW_MIN} min)", str(recent_errors)))
        if recent_errors >= RECENT_ERRORS_WARN:
            level = "down" if recent_errors >= RECENT_ERRORS_DOWN else "warn"
            if web_status == "ok" or (level == "down" and web_status == "warn"):
                web_status = level
            alerts.append({
                "level": level, "node": "webapp",
                "title": f"{recent_errors} erro{'s' if recent_errors != 1 else ''} nos últimos {RECENT_ERRORS_WINDOW_MIN} min",
                "action": "Peça para a IA investigar.",
                "investigate": True,
            })
    if primary_language:
        web_facts.append(("Tecnologia", primary_language))

    # ---- Servidor ------------------------------------------------------
    infra_status = _worst([by_key[k]["status"] for k in ("cpu", "memory", "disk")])
    for key in ("cpu", "memory", "disk", "gpu"):
        r = by_key[key]
        if r["status"] not in ("warn", "down"):
            continue
        warn, crit = THRESHOLDS[key]
        alerts.append({
            "level": r["status"], "node": "infra", "resource": key,
            "title": f"{r['label']} em {r['display']}",
            "detail": f"Atenção a partir de {warn}%, crítico a partir de {crit}%.",
            "action": RESOURCE_ADVICE[key],
        })
    infra_facts = [("Máquina", host)] + [
        (by_key[k]["label"], by_key[k]["display"]) for k in ("cpu", "memory", "disk")
    ]

    # ---- TracePilot (conexão) ------------------------------------------
    conn = _connection(openobserve.get("up", False), agent_reporting, sources)
    tp_facts = [("Conexão", conn["text"]), ("Origem", conn["via"] or "—")]
    tp_facts.append(("Agente instalado", "enviando dados" if agent_reporting else "não"))
    if sources is not None:
        tp_facts.append(("API de ingestão", "recebendo" if sources.get("direct_api") else "sem uso"))
        tp_facts.append((
            f"Registros ({RECENT_ERRORS_WINDOW_MIN} min)",
            f"{sources.get('logs', 0)} logs · {sources.get('traces', 0)} rastros",
        ))
    if conn["status"] == "down":
        alerts.append({
            "level": "warn", "node": "tracepilot",
            "title": "TracePilot sem armazenamento",
            "action": "Suba o OpenObserve: docker compose up -d",
        })
    elif conn["status"] == "warn":
        alerts.append({
            "level": "warn", "node": "tracepilot",
            "title": "Nenhum dado chegando do sistema",
            "action": "Instale o agente ou conecte a aplicação pela API.",
        })

    nodes = {
        "users": {
            "title": "Usuários", "subtitle": "quem acessa",
            "status": web_status,
            "what": "Quem usa o sistema. O status acompanha o do site.",
            "facts": [],
        },
        "webapp": {
            "title": "Site / App", "subtitle": system_name,
            "status": web_status,
            "what": "As páginas e a lógica do seu sistema.",
            "facts": web_facts,
        },
        "database": {
            "title": "Banco de dados", "subtitle": "pedidos, cadastros",
            "status": "unknown",
            "what": "Ainda não monitorado diretamente. Falhas aparecem como erros do site.",
            "facts": [],
        },
        "infra": {
            "title": "Servidor", "subtitle": host,
            "status": infra_status,
            "what": "A máquina onde tudo roda.",
            "facts": infra_facts,
        },
        "tracepilot": {
            "title": "TracePilot",
            "subtitle": ("via " + conn["via"]) if len(conn["channels"]) == 1 else (conn["via"] or conn["text"].lower()),
            "status": conn["status"],
            "status_text_override": conn["text"],
            "what": "Recebe os dados, guarda o histórico e investiga problemas.",
            "facts": tp_facts,
        },
    }
    for key, node in nodes.items():
        node["status_text"] = node.pop("status_text_override", None) or STATUS_TEXT[node["status"]]
        node["status_icon"] = STATUS_ICON[node["status"]]

    level_order = {"down": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: level_order[a["level"]])
    problems = [a for a in alerts if a["level"] == "down"]
    risks = [a for a in alerts if a["level"] == "warn"]
    if problems:
        overall = {"status": "down", "headline": problems[0]["title"]}
    elif risks:
        overall = {"status": "warn", "headline": f"{len(risks)} ponto{'s' if len(risks) > 1 else ''} de atenção"}
    else:
        overall = {"status": "ok", "headline": "Tudo normal"}

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
        "connection": conn,
        "recent_errors": recent_errors,
        "tech": tech,
        "system_name": system_name,
    }


def example_state() -> dict:
    """Estado ilustrativo para a landing page (nunca dado real): site no ar
    com erros recentes e disco perto do limite."""
    def leaf(v, src="agent"):
        return {"value": v, "source": src, "label": ""}

    gb = 1024**3
    snapshot = {
        "host_name": leaf("vps-loja"),
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
    return build_state(
        profile={"system_name": "Loja da Ana"},
        demo_app={"up": True, "url": "https://lojadaana.com.br", "latency_ms": 180},
        openobserve={"up": True, "streams": []},
        snapshot=snapshot,
        agent_reporting=True,
        recent_errors=3,
        sources={"logs": 120, "traces": 340, "direct_api": False},
        history=store,
    )
