"""Detecção de tráfego suspeito a partir das requisições HTTP reais do
sistema monitorado (spans de servidor no OpenObserve).

Regras determinísticas, explicáveis em uma frase cada:

- tentativa de invasão: o caminho/consulta traz assinatura de ataque
  (arquivo sensível, path traversal, SQL injection, XSS, injeção de
  comando, Log4Shell) ou o user-agent é de ferramenta de ataque;
- robô/crawler: user-agent de automação (curl, python-requests, scrapy,
  headless...) — buscadores conhecidos (Googlebot, Bingbot) ficam à parte;
- varredura: muitos 404 vindos do mesmo IP;
- força bruta: muitos 401/403 vindos do mesmo IP.

Tráfego sintético conhecido (o gerador de carga da demo) é ignorado via
`TRAFFIC_ALLOWED_AGENTS`. Não bloqueia nada: só aponta, com IP, o que foi
tentado e a orientação de como reagir.
"""
import os
import re
import time
from collections import defaultdict
from urllib.parse import unquote_plus, urlsplit

ALLOWED_AGENTS = [
    a.strip().lower()
    for a in os.getenv("TRAFFIC_ALLOWED_AGENTS", "tracepilot-loadgen").split(",")
    if a.strip()
]
SCAN_404_MIN = 15
BRUTE_FORCE_MIN = 10

_ATTACK_PATTERNS = [
    ("arquivo sensível", re.compile(r"/\.(env|git|svn|htaccess|aws|ssh)\b|/wp-(login|admin|config)|/phpmyadmin|/server-status|/actuator|/config\.(json|php|yml)|\.(sql|bak|old)(\?|$)", re.I)),
    ("path traversal", re.compile(r"\.\./|\.\.%2f|/etc/passwd|/proc/self", re.I)),
    ("SQL injection", re.compile(r"('|%27)\s*(or|and)\s*'?\d+'?\s*=\s*'?\d+|union(\s|\+)+select|sleep\(\d+\)|;\s*drop\s+table|--\s*$", re.I)),
    ("XSS", re.compile(r"<script|javascript:|onerror\s*=|onload\s*=|<svg/onload", re.I)),
    ("injeção de comando", re.compile(r"(;|\||`|\$\()\s*(cat|id|whoami|wget|curl|nc|bash|sh)\b", re.I)),
    ("Log4Shell", re.compile(r"\$\{jndi:", re.I)),
]
_ATTACK_TOOLS = re.compile(r"sqlmap|nikto|nmap|masscan|zgrab|nuclei|dirbuster|gobuster|wpscan|acunetix|hydra|metasploit|fuzz", re.I)
_GOOD_BOTS = re.compile(r"googlebot|bingbot|duckduckbot|yandexbot|applebot|baiduspider", re.I)
_BOTS = re.compile(r"bot|crawler|spider|scrapy|curl|wget|python-requests|python-httpx|httpx|aiohttp|go-http-client|java/|okhttp|headless|phantomjs|libwww|postman", re.I)

CATEGORY_TEXT = {
    "attack": "Tentativa de invasão",
    "bruteforce": "Força bruta",
    "scan": "Varredura",
    "bot": "Robô / crawler",
    "search": "Buscador",
}
CATEGORY_ADVICE = {
    "attack": "Bloqueie o IP no firewall ou na CDN e confira se a rota atacada valida a entrada.",
    "bruteforce": "Bloqueie o IP e limite tentativas de login (rate limit).",
    "scan": "Bloqueie o IP; robôs de varredura procuram arquivos esquecidos no servidor.",
    "bot": "Se não for seu, limite a taxa (rate limit) ou bloqueie pelo user-agent.",
    "search": "Normal: buscadores indexando o site.",
}


def _target(req: dict) -> str:
    """Caminho + query. `http_target` vem sem a query; `http_url` tem tudo."""
    url = req.get("http_url")
    if url:
        parts = urlsplit(url)
        return parts.path + (f"?{parts.query}" if parts.query else "")
    return req.get("http_target") or ""


_SUCCESS_MATTERS = {"arquivo sensível", "path traversal"}


def _classify(req: dict) -> tuple[str, str] | None:
    ua = (req.get("http_user_agent") or "").strip()
    if any(a in ua.lower() for a in ALLOWED_AGENTS):
        return None
    target = unquote_plus(_target(req))
    if _ATTACK_TOOLS.search(ua):
        return "attack", f"ferramenta de ataque ({_ATTACK_TOOLS.search(ua).group(0)})"
    for label, rx in _ATTACK_PATTERNS:
        if rx.search(target):
            return "attack", label
    if _GOOD_BOTS.search(ua):
        return "search", "buscador"
    if not ua or _BOTS.search(ua):
        return "bot", "user-agent de automação" if ua else "sem user-agent"
    return None


def analyze(requests: list[dict]) -> dict:
    groups: dict[tuple[str, str], dict] = {}
    by_ip_status: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add(category, ip, reason, req):
        g = groups.setdefault((ip, category), {
            "category": category, "category_text": CATEGORY_TEXT[category], "ip": ip,
            "count": 0, "reasons": set(), "samples": [], "user_agent": "", "last_seen": 0,
            "success": False, "advice": CATEGORY_ADVICE[category],
        })
        g["count"] += 1
        g["reasons"].add(reason)
        target = unquote_plus(_target(req))
        if target and target not in g["samples"] and len(g["samples"]) < 3:
            g["samples"].append(target[:90])
        ua = req.get("http_user_agent") or ""
        if category == "attack" and (_ATTACK_TOOLS.search(ua) or not g["user_agent"]):
            g["user_agent"] = ua[:80]
        g["user_agent"] = g["user_agent"] or ua[:80]
        g["last_seen"] = max(g["last_seen"], (req.get("_timestamp") or 0) / 1_000_000)
        # 2xx só indica possível sucesso quando o alvo era um arquivo/caminho
        # sensível; um ?q=<script> respondido pela listagem não é invasão.
        if (category == "attack" and reason in _SUCCESS_MATTERS
                and str(req.get("http_status_code", "")).startswith("2")):
            g["success"] = True

    for req in requests:
        ip = req.get("net_peer_ip") or "desconhecido"
        ua = (req.get("http_user_agent") or "").lower()
        if any(a in ua for a in ALLOWED_AGENTS):
            continue
        by_ip_status[ip][str(req.get("http_status_code", ""))] += 1
        result = _classify(req)
        if result:
            add(result[0], ip, result[1], req)

    for ip, statuses in by_ip_status.items():
        denied = statuses.get("401", 0) + statuses.get("403", 0)
        if denied >= BRUTE_FORCE_MIN:
            g = groups.setdefault((ip, "bruteforce"), {
                "category": "bruteforce", "category_text": CATEGORY_TEXT["bruteforce"], "ip": ip,
                "count": denied, "reasons": {f"{denied} acessos negados (401/403)"}, "samples": [],
                "user_agent": "", "last_seen": time.time(), "success": False, "advice": CATEGORY_ADVICE["bruteforce"],
            })
        not_found = statuses.get("404", 0)
        if not_found >= SCAN_404_MIN:
            groups.setdefault((ip, "scan"), {
                "category": "scan", "category_text": CATEGORY_TEXT["scan"], "ip": ip,
                "count": not_found, "reasons": {f"{not_found} páginas inexistentes (404)"}, "samples": [],
                "user_agent": "", "last_seen": time.time(), "success": False, "advice": CATEGORY_ADVICE["scan"],
            })

    order = {"attack": 0, "bruteforce": 1, "scan": 2, "bot": 3, "search": 4}
    events = sorted(groups.values(), key=lambda g: (order[g["category"]], -g["count"]))
    for e in events:
        e["reasons"] = ", ".join(sorted(e["reasons"]))

    count = lambda cat: sum(e["count"] for e in events if e["category"] == cat)  # noqa: E731
    attacks = count("attack")
    hostile = attacks + count("bruteforce") + count("scan")
    bots = count("bot")
    if any(e["success"] for e in events) or count("bruteforce"):
        level = "down"
    elif hostile:
        level = "down" if attacks else "warn"
    elif bots:
        level = "warn"
    else:
        level = "ok"
    return {
        "level": level,
        "total_requests": len(requests),
        "attacks": attacks,
        "hostile_ips": len({e["ip"] for e in events if e["category"] in ("attack", "bruteforce", "scan")}),
        "bots": bots,
        "search_bots": count("search"),
        "bruteforce": count("bruteforce"),
        "scans": count("scan"),
        "events": events[:8],
    }
