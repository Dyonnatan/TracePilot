#!/usr/bin/env bash
# Sobe (ou derruba) a demo completa do TracePilot com a loja Apex Space:
#
#   telemetria   OpenObserve + OTel Collector (docker-compose.yml da raiz)
#   loja         ambiente de referência (branch feat/reference-environment,
#                rodando de um worktree em .worktrees/, sem tocar na branch atual)
#   Collector    TracePilot Collector (local-agent, Rust) neste host
#   API          TracePilot API (ingest/, porta 8810)
#   painel       TracePilot (webapp/, porta 8800)
#
# Uso: scripts/demo.sh up | down | status
#
# Processos locais rodam com nohup/setsid (sobrevivem ao terminal), com
# PID e log em workspace/run/. Credenciais do OpenObserve: as de dev do
# .env.example, a menos que o .env defina outras.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$ROOT/workspace/run"
WORKTREE="$ROOT/.worktrees/reference-environment"
BRANCH="origin/feat/reference-environment"
mkdir -p "$RUN"
cd "$ROOT"

if [[ -f .env ]]; then set -a; source .env; set +a; fi
export OPENOBSERVE_URL="${OPENOBSERVE_URL:-http://localhost:5080}"
export OPENOBSERVE_USER="${OPENOBSERVE_USER:-admin@tracepilot.local}"
export OPENOBSERVE_PASSWORD="${OPENOBSERVE_PASSWORD:-ChangeMe123!}"
export LLM_BACKEND="${LLM_BACKEND:-local}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3:4b}"
export PYTHONUNBUFFERED=1

start_proc() {  # nome, comando...
  local name="$1"; shift
  if [[ -f "$RUN/$name.pid" ]] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
    echo "  $name já está rodando (pid $(cat "$RUN/$name.pid"))"; return
  fi
  setsid nohup "$@" >"$RUN/$name.log" 2>&1 < /dev/null &
  echo $! >"$RUN/$name.pid"
  echo "  $name iniciado (pid $!, log workspace/run/$name.log)"
}

stop_proc() {
  local name="$1"
  if [[ -f "$RUN/$name.pid" ]]; then
    kill "$(cat "$RUN/$name.pid")" 2>/dev/null && echo "  $name parado" || true
    rm -f "$RUN/$name.pid"
  fi
}

free_port() {  # derruba quem estiver ouvindo na porta (ex.: instância antiga sem pidfile)
  local pid
  pid=$(ss -ltnp 2>/dev/null | grep ":$1 " | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1 || true)
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null && echo "  porta $1 liberada (pid $pid)" || true
}

check() {  # rótulo, url
  if curl -s -o /dev/null -m 3 -f "$2"; then echo "  ok    $1  $2"; else echo "  FALHA $1  $2"; fi
}

status() {
  echo "Serviços:"
  check "Painel TracePilot " http://localhost:8800/login
  check "TracePilot API    " http://localhost:8810/v1/health
  check "Loja Apex         " http://localhost:8088/health
  check "Painel de falhas  " http://localhost:8090/
  check "OpenObserve       " http://localhost:5080/healthz
  if [[ -f "$RUN/collector.pid" ]] && kill -0 "$(cat "$RUN/collector.pid")" 2>/dev/null; then
    echo "  ok    TracePilot Collector (pid $(cat "$RUN/collector.pid"))"
  else
    echo "  FALHA TracePilot Collector (não está rodando)"
  fi
}

case "${1:-}" in
  up)
    echo "1/5 Telemetria (OpenObserve + Collector OTel)"
    if ! docker ps --format '{{.Names}}' | grep -qx tracepilot-openobserve; then
      docker compose up -d
    else
      echo "  já está de pé"
    fi
    docker network inspect tracepilot >/dev/null 2>&1 || docker network create tracepilot >/dev/null
    docker network connect --alias otel-collector tracepilot tracepilot-otel-collector 2>/dev/null || true

    echo "2/5 Loja Apex Space (ambiente de referência)"
    if [[ ! -d "$WORKTREE" ]]; then
      git fetch -q origin feat/reference-environment
      git worktree add -q --detach "$WORKTREE" "$BRANCH"
      grep -qx ".worktrees/" .git/info/exclude || echo ".worktrees/" >> .git/info/exclude
    fi
    (cd "$WORKTREE/demo_app" && docker compose up -d --build --quiet-pull 2>&1 | grep -E "Started|Running|Error" || true)

    echo "3/5 TracePilot Collector"
    [[ -x local-agent/target/release/tracepilot-agent ]] || (cd local-agent && cargo build --release -q)
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 OTEL_SERVICE_NAME=tracepilot-local-agent \
      start_proc collector local-agent/target/release/tracepilot-agent

    echo "4/5 TracePilot API (porta 8810)"
    [[ -f "$RUN/api.pid" ]] || free_port 8810
    TRACEPILOT_OTLP_HTTP_ENDPOINT=http://localhost:4318 \
      start_proc api .venv/bin/uvicorn ingest.main:app --host 127.0.0.1 --port 8810

    echo "5/5 Painel TracePilot (porta 8800)"
    [[ -f "$RUN/painel.pid" ]] || free_port 8800
    start_proc painel .venv/bin/uvicorn webapp.main:app --host 127.0.0.1 --port 8800

    sleep 3
    status
    echo
    echo "Abra http://localhost:8800"
    ;;
  down)
    stop_proc painel; stop_proc api; stop_proc collector
    if [[ -d "$WORKTREE/demo_app" ]]; then (cd "$WORKTREE/demo_app" && docker compose down); fi
    echo "Telemetria (OpenObserve) continua de pé; para derrubar: docker compose down"
    ;;
  status)
    status
    ;;
  *)
    echo "uso: scripts/demo.sh up | down | status" >&2; exit 1
    ;;
esac
