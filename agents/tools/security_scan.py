"""Análise de segurança do sistema monitorado, para o onboarding e o painel.

Três frentes, todas checagens determinísticas (sem LLM, sem chutar):

- código: varredura estática da cópia local do repositório (segredos no
  código, SQL montado com texto, eval/shell, CORS aberto, debug ligado,
  container como root, senha padrão, dependências sem versão fixa);
- site: requisições HTTP de leitura ao endereço do sistema (HTTPS,
  cabeçalhos de segurança, versão do servidor exposta, arquivos sensíveis
  acessíveis como /.env e /.git);
- servidor: portas de banco de dados abertas para a rede, no host onde o
  painel roda (mesma ressalva de `resource_snapshot`: em demo, é a mesma
  máquina).

Cada achado vem com severidade (critical > high > medium > low), onde
está, por que importa e como corrigir, em português simples, e já sai
ordenado por urgência. Nunca levanta exceção: uma frente que falha só
some do resultado e fica registrada em `checks`.
"""
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEVERITY_LABEL = {"critical": "Crítico", "high": "Alto", "medium": "Médio", "low": "Baixo"}
URGENCY_LABEL = {
    "critical": "Corrigir agora",
    "high": "Corrigir esta semana",
    "medium": "Planejar",
    "low": "Quando der",
}

_TEXT_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".java", ".go", ".rb", ".php", ".cs",
             ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".env", ".sh", ".sql", ".html"}
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
_MAX_FILE = 300_000

# (id, severidade, regex, título, por quê, como corrigir, aplicar só em sufixos)
_CODE_RULES = [
    ("private-key", "critical", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
     "Chave privada dentro do código",
     "Quem tiver acesso ao código consegue se passar pelo seu servidor ou entrar nele.",
     "Remova a chave do repositório, gere uma nova e guarde em variável de ambiente ou cofre de segredos.", None),
    ("aws-key", "critical", re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     "Chave de acesso da AWS no código",
     "Dá acesso à sua conta na nuvem; robôs procuram isso em repositórios o tempo todo.",
     "Revogue a chave no painel da AWS agora e use variável de ambiente.", None),
    ("hardcoded-secret", "high",
     re.compile(r"""(?i)\b(password|passwd|secret|api[_-]?key|token|auth[_-]?key)\b["']?\s*[:=]\s*["'][^"'\s$<>{}]{4,}["']"""),
     "Senha ou chave escrita direto no código",
     "Fica visível para qualquer pessoa com acesso ao repositório e vaza junto com ele.",
     "Leia o valor de uma variável de ambiente (.env fora do git).", {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".php", ".cs"}),
    ("sql-injection", "high",
     re.compile(r"""\.execute\(\s*(?:f(["'])(?P<fbody>.*?)\1|["'][^"']*["']\s*(?:%|\+|\.format))"""),
     "Consulta SQL montada com texto do usuário",
     "Permite SQL injection: um atacante pode ler ou apagar o banco inteiro.",
     "Use parâmetros na consulta (ex.: execute(\"... WHERE id = %s\", (id,))).", {".py"}),
    ("dangerous-eval", "high", re.compile(r"(?<![\w.])(?:eval|exec)\(\s*(?:request|input|data|payload|body)"),
     "Código executa texto vindo de fora (eval/exec)",
     "Um atacante pode rodar qualquer comando no servidor.",
     "Remova eval/exec; trate a entrada como dado, nunca como código.", {".py", ".js", ".ts"}),
    ("shell-true", "high", re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"),
     "Comando do sistema com shell=True",
     "Se algum pedaço do comando vier do usuário, ele consegue executar comandos no servidor.",
     "Passe a lista de argumentos sem shell=True.", {".py"}),
    ("unsafe-yaml", "medium", re.compile(r"yaml\.load\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)"),
     "Leitura de YAML insegura",
     "yaml.load sem SafeLoader pode executar código embutido no arquivo.",
     "Troque por yaml.safe_load.", {".py"}),
    ("pickle", "medium", re.compile(r"pickle\.loads?\("),
     "Uso de pickle",
     "Carregar pickle de fonte não confiável executa código arbitrário.",
     "Use JSON para dados vindos de fora.", {".py"}),
    ("cors-any", "medium", re.compile(r"""allow_origins\s*=\s*\[\s*["']\*["']\s*\]|Access-Control-Allow-Origin["']?\s*[:,]\s*["']\*"""),
     "CORS liberado para qualquer site",
     "Qualquer página da internet pode chamar sua API a partir do navegador do usuário.",
     "Liste só os domínios do seu front-end em allow_origins.", None),
    ("debug-on", "medium", re.compile(r"(?i)\bdebug\s*=\s*True\b|\bDEBUG\s*=\s*(?:True|1|['\"]true['\"])"),
     "Modo debug ligado",
     "Mostra detalhes internos (código, variáveis) para quem provocar um erro.",
     "Desligue o debug em produção (via variável de ambiente).", None),
    ("tls-off", "medium", re.compile(r"verify\s*=\s*False"),
     "Verificação de certificado desligada",
     "Permite que alguém no meio do caminho leia ou altere as chamadas.",
     "Remova verify=False.", {".py"}),
]

_DEFAULT_PASSWORDS = {"shop", "postgres", "password", "admin", "123456", "root", "changeme", "changeme123!", "secret", "test"}
_DB_PORTS = {27017: "MongoDB", 5432: "PostgreSQL", 3306: "MySQL", 6379: "Redis", 9200: "Elasticsearch", 1433: "SQL Server"}


def _finding(fid, severity, title, where, why, fix, area) -> dict:
    return {
        "id": fid,
        "severity": severity,
        "severity_label": SEVERITY_LABEL[severity],
        "urgency": URGENCY_LABEL[severity],
        "title": title,
        "where": where,
        "why": why,
        "fix": fix,
        "area": area,
    }


def _first_unsafe_sql(rx: re.Pattern, text: str) -> re.Match | None:
    """f-string que só interpola CONSTANTES (ex.: lista de colunas) não é
    injeção — o valor do usuário vai por parâmetro. Só conta se houver
    alguma variável comum dentro das chaves, ou concatenação/%/format."""
    for m in rx.finditer(text):
        body = m.group("fbody")
        if body is None:
            return m
        exprs = re.findall(r"\{([^{}]+)\}", body)
        if any(not re.fullmatch(r"[A-Z_][A-Z0-9_]*", e.strip()) for e in exprs):
            return m
    return None


def _repo_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "."],
                             capture_output=True, text=True, timeout=5, check=True)
        files = [root / f for f in out.stdout.split("\0") if f]
        if files:
            return files
    except (OSError, subprocess.SubprocessError):
        pass
    return [p for p in root.rglob("*") if p.is_file() and not (set(p.parts) & _SKIP_DIRS)]


def _scan_code(root: Path) -> list[dict]:
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    unpinned: list[tuple[str, int]] = []
    files = _repo_files(root)

    for path in files:
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        name = path.name
        if name == ".env" or (name.startswith(".env") and not name.endswith(".example")):
            findings.append(_finding("env-committed", "high", "Arquivo .env no repositório", rel,
                                     "Costuma guardar senhas e chaves; quem vê o repositório vê os segredos.",
                                     "Tire o .env do git (git rm --cached) e adicione ao .gitignore.", "código"))
        if name == "Dockerfile":
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            if not re.search(r"(?m)^\s*USER\s+(?!root\b)\S+", text):
                findings.append(_finding("docker-root", "medium", "Container roda como root", rel,
                                         "Se alguém invadir a aplicação, já entra com poder total no container.",
                                         "Crie um usuário sem privilégio e adicione USER no Dockerfile.", "código"))
            continue
        if name.startswith("requirements") and name.endswith(".txt"):
            try:
                lines = [l.strip() for l in path.read_text(errors="ignore").splitlines()]
            except OSError:
                continue
            loose = [l for l in lines if l and not l.startswith(("#", "-")) and "==" not in l]
            if loose:
                unpinned.append((rel, len(loose)))
            continue
        if path.suffix.lower() not in _TEXT_EXT and name not in ("docker-compose.yml", "compose.yml"):
            continue
        try:
            if path.stat().st_size > _MAX_FILE:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue

        if name.endswith((".yml", ".yaml")):
            for m in re.finditer(r"(?i)(POSTGRES_PASSWORD|MYSQL_ROOT_PASSWORD|MONGO_INITDB_ROOT_PASSWORD|ZO_ROOT_USER_PASSWORD)\s*:\s*\$?\{?[^}\n]*?:-?([^}\s\"']+)?", text):
                default = (m.group(2) or "").strip().lower()
                if default in _DEFAULT_PASSWORDS:
                    key = ("default-password", rel)
                    if key not in seen:
                        seen.add(key)
                        line = text[: m.start()].count("\n") + 1
                        findings.append(_finding("default-password", "high", "Senha padrão no banco de dados",
                                                 f"{rel}:{line}",
                                                 "Senhas padrão são as primeiras que um invasor tenta.",
                                                 "Defina uma senha forte por variável de ambiente, sem valor padrão.", "código"))

        for fid, severity, rx, title, why, fix, suffixes in _CODE_RULES:
            if suffixes and path.suffix.lower() not in suffixes:
                continue
            m = rx.search(text)
            if not m:
                continue
            snippet = m.group(0)
            if fid == "hardcoded-secret" and re.search(r"(?i)example|placeholder|your[-_]|xxx|<|\.\.\.", snippet):
                continue
            if fid == "sql-injection":
                m = _first_unsafe_sql(rx, text)
                if not m:
                    continue
            key = (fid, rel)
            if key in seen:
                continue
            seen.add(key)
            line = text[: m.start()].count("\n") + 1
            findings.append(_finding(fid, severity, title, f"{rel}:{line}", why, fix, "código"))
    if unpinned:
        total = sum(n for _, n in unpinned)
        findings.append(_finding("unpinned-deps", "low", "Dependências sem versão fixa",
                                 f"{total} pacotes em {len(unpinned)} arquivo{'s' if len(unpinned) > 1 else ''}",
                                 "Uma atualização automática pode trazer uma falha de segurança ou quebrar o sistema.",
                                 "Fixe as versões (pip freeze) e atualize de forma planejada.", "código"))
    return findings


def _scan_site(url: str) -> list[dict]:
    findings: list[dict] = []
    parsed = urlparse(url)
    host = parsed.hostname or ""
    local = host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")
    try:
        resp = httpx.get(url, timeout=4, follow_redirects=True)
    except httpx.HTTPError:
        return findings

    if parsed.scheme != "https":
        findings.append(_finding(
            "no-https", "low" if local else "high", "Site sem HTTPS", url,
            "Senhas e dados trafegam sem criptografia." + (" Aceitável só em ambiente local." if local else ""),
            "Ative HTTPS (ex.: Let's Encrypt, ou o proxy/CDN da hospedagem).", "site"))

    headers = {k.lower(): v for k, v in resp.headers.items()}
    if "content-security-policy" not in headers:
        findings.append(_finding("no-csp", "medium", "Sem Content-Security-Policy", url,
                                 "Facilita ataques que injetam scripts na página (XSS).",
                                 "Adicione o cabeçalho Content-Security-Policy no servidor ou proxy.", "site"))
    if "x-frame-options" not in headers and "frame-ancestors" not in headers.get("content-security-policy", ""):
        findings.append(_finding("no-frame", "low", "Página pode ser embutida por outro site", url,
                                 "Permite clickjacking: um site falso põe o seu por baixo e engana o clique.",
                                 "Adicione X-Frame-Options: DENY (ou frame-ancestors no CSP).", "site"))
    if "x-content-type-options" not in headers:
        findings.append(_finding("no-nosniff", "low", "Falta X-Content-Type-Options", url,
                                 "O navegador pode interpretar arquivos de um jeito perigoso.",
                                 "Adicione X-Content-Type-Options: nosniff.", "site"))
    if parsed.scheme == "https" and "strict-transport-security" not in headers:
        findings.append(_finding("no-hsts", "medium", "Falta HSTS", url,
                                 "O primeiro acesso pode ser desviado para HTTP sem criptografia.",
                                 "Adicione Strict-Transport-Security.", "site"))
    server = headers.get("server", "")
    if re.search(r"\d", server):
        findings.append(_finding("server-version", "low", "Servidor revela a versão", f"Server: {server}",
                                 "Ajuda o atacante a procurar falhas conhecidas daquela versão.",
                                 "Esconda a versão no cabeçalho Server.", "site"))

    base = url.rstrip("/")
    probes = [
        ("/.env", "critical", "Arquivo .env acessível pela internet", r"(?m)^[A-Z_]+=", "env-exposed"),
        ("/.git/config", "critical", "Pasta .git acessível pela internet", r"\[core\]", "git-exposed"),
        ("/docs", "low", "Documentação da API aberta ao público", r"(?i)swagger|redoc|openapi", "docs-public"),
    ]
    for path, severity, title, marker, fid in probes:
        try:
            r = httpx.get(base + path, timeout=3)
        except httpx.HTTPError:
            continue
        if r.status_code == 200 and re.search(marker, r.text[:5000]):
            why = {
                "env-exposed": "Qualquer um baixa as senhas e chaves do sistema.",
                "git-exposed": "Dá para baixar todo o código-fonte, inclusive segredos no histórico.",
                "docs-public": "Mostra a qualquer um todas as rotas da API, o que facilita encontrar uma brecha.",
            }[fid]
            fix = {
                "env-exposed": "Bloqueie o acesso ao arquivo no servidor e troque todas as senhas que estavam nele.",
                "git-exposed": "Bloqueie /.git no servidor web e não publique a pasta do repositório.",
                "docs-public": "Proteja /docs com login ou desative em produção.",
            }[fid]
            findings.append(_finding(fid, severity, title, base + path, why, fix, "site"))
    return findings


def _scan_ports() -> list[dict]:
    findings: list[dict] = []
    try:
        out = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return findings
    exposed: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        addr = parts[3]
        host, _, port = addr.rpartition(":")
        if host in ("0.0.0.0", "*", "[::]") and port.isdigit() and int(port) in _DB_PORTS:
            exposed.add(int(port))
    for port in sorted(exposed):
        findings.append(_finding(
            "db-exposed", "high", f"{_DB_PORTS[port]} aberto para a rede", f"porta {port}",
            "Bancos de dados expostos são alvo de robôs que testam senhas e sequestram os dados.",
            f"Publique a porta só em 127.0.0.1 (ex.: \"127.0.0.1:{port}:{port}\" no Docker) ou feche no firewall.",
            "servidor"))
    return findings


def scan(app_url: str | None = None, repo_path: str | None = None, repo_paths: list[str] | None = None) -> dict:
    findings: list[dict] = []
    checks = []
    paths = [p for p in (repo_paths or ([repo_path] if repo_path else [])) if p and Path(p).is_dir()]
    for path in paths:
        try:
            code = _scan_code(Path(path))
            if len(paths) > 1:  # vários repositórios: diz de qual veio
                for f in code:
                    f["where"] = f"{Path(path).name}/{f['where']}"
            findings += code
            checks.append({"area": "código", "ok": True, "detail": Path(path).name + "/"})
        except Exception as exc:  # noqa: BLE001 — uma frente não derruba as outras
            checks.append({"area": "código", "ok": False, "detail": str(exc)[:80]})
    if app_url:
        try:
            findings += _scan_site(app_url)
            checks.append({"area": "site", "ok": True, "detail": app_url})
        except Exception as exc:  # noqa: BLE001
            checks.append({"area": "site", "ok": False, "detail": str(exc)[:80]})
    try:
        findings += _scan_ports()
        checks.append({"area": "servidor", "ok": True, "detail": "portas abertas"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"area": "servidor", "ok": False, "detail": str(exc)[:80]})

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["area"], f["title"]))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}
    return {"checked_at": time.time(), "findings": findings, "counts": counts, "checks": checks}


def fix_prompt(finding: dict, system_name: str | None = None) -> str:
    """Prompt pronto para colar na IA que mantém o código (mesma ideia do
    prompt de correção das investigações)."""
    return (
        f"Corrija esta falha de segurança{' no sistema ' + system_name if system_name else ''}, "
        f"apontada pelo TracePilot (severidade: {finding['severity_label']}).\n\n"
        f"Problema: {finding['title']}\n"
        f"Onde: {finding['where']}\n"
        f"Por que importa: {finding['why']}\n"
        f"Como corrigir: {finding['fix']}\n\n"
        "Faça a menor mudança que resolve, sem quebrar o que já funciona, e explique o que mudou."
    )
