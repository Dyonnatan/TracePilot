"""Flags de falha do shop-api, ligadas pelo chaos-control.

O canal é um servidor HTTP da stdlib numa porta interna (não publicada no
compose) e sem OpenTelemetry: ligar uma flag não deixa rastro na telemetria.
Quem quiser registrar a mudança (ex.: change.event de feature flag) usa
FaultRegistry.on_change.
"""
import json
import os
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAULTS_PORT = int(os.getenv("FAULTS_PORT", "8081"))

CATALOG_N_PLUS_ONE = "catalog_n_plus_one"
AUDIT_SYNC_WRITE = "audit_sync_write"
PRODUCT_CACHE_UNBOUNDED = "product_cache_unbounded"
PAYMENT_RETRY_NO_BACKOFF = "payment_retry_no_backoff"
DEBUG_PAYLOAD_LOGGING = "debug_payload_logging"
KNOWN_FLAGS = frozenset(
    {CATALOG_N_PLUS_ONE, AUDIT_SYNC_WRITE, PRODUCT_CACHE_UNBOUNDED, PAYMENT_RETRY_NO_BACKOFF, DEBUG_PAYLOAD_LOGGING}
)


class UnknownFlag(KeyError):
    pass


class FaultRegistry:
    def __init__(self, known: frozenset[str] = KNOWN_FLAGS) -> None:
        self._known = known
        self._flags: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._listeners: list[Callable[[str, bool, dict], None]] = []

    def config(self, name: str) -> dict | None:
        """Configuração da flag se ela estiver ligada; None se desligada."""
        with self._lock:
            return self._flags.get(name)

    def enabled(self, name: str) -> bool:
        return self.config(name) is not None

    def set(self, name: str, enabled: bool, config: dict | None = None) -> dict:
        if name not in self._known:
            raise UnknownFlag(name)
        with self._lock:
            was_enabled = name in self._flags
            if enabled:
                self._flags[name] = dict(config or {})
            else:
                self._flags.pop(name, None)
        if enabled != was_enabled:
            for listener in self._listeners:
                listener(name, enabled, dict(config or {}))
        return self.describe(name)

    def describe(self, name: str) -> dict:
        config = self.config(name)
        return {"name": name, "enabled": config is not None, "config": config or {}}

    def snapshot(self) -> list[dict]:
        return [self.describe(name) for name in sorted(self._known)]

    def on_change(self, listener: Callable[[str, bool, dict], None]) -> None:
        self._listeners.append(listener)


registry = FaultRegistry()


def _handler_for(target: FaultRegistry) -> type[BaseHTTPRequestHandler]:
    class FaultsHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

        def _reply(self, status: int, body: object) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/faults":
                self._reply(200, target.snapshot())
            else:
                self._reply(404, {"detail": "not found"})

        def do_POST(self) -> None:
            prefix = "/faults/"
            if not self.path.startswith(prefix):
                self._reply(404, {"detail": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                state = target.set(self.path[len(prefix) :], bool(body["enabled"]), body.get("config"))
            except UnknownFlag as exc:
                self._reply(404, {"detail": f"flag desconhecida: {exc.args[0]}"})
            except (KeyError, TypeError, ValueError) as exc:
                self._reply(400, {"detail": f"corpo inválido: {exc}"})
            else:
                self._reply(200, state)

    return FaultsHandler


def start_server(target: FaultRegistry = registry, port: int = FAULTS_PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _handler_for(target))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="faults-server", daemon=True).start()
    return server
