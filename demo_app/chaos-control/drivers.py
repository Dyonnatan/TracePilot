"""Drivers que aplicam e removem cada tipo de falha. Nenhum deles passa
pelos serviços instrumentados de forma visível na telemetria.
"""
import logging
import threading
from typing import Protocol

import httpx
import psycopg
from psycopg import sql

logger = logging.getLogger("chaos.drivers")


class ManualActionRequired(Exception):
    def __init__(self, command: str) -> None:
        super().__init__(f"ação manual necessária: rode `{command}` em demo_app/")
        self.command = command


class Driver(Protocol):
    def enable(self, params: dict) -> None: ...

    def disable(self, params: dict) -> None: ...


class ToxiproxyDriver:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def enable(self, params: dict) -> None:
        response = self._client.post(
            f"/proxies/{params['proxy']}/toxics",
            json={
                "name": params["toxic"],
                "type": params["type"],
                "stream": params.get("stream", "downstream"),
                "toxicity": 1.0,
                "attributes": params.get("attributes", {}),
            },
        )
        if response.status_code != 409:
            response.raise_for_status()

    def disable(self, params: dict) -> None:
        response = self._client.delete(f"/proxies/{params['proxy']}/toxics/{params['toxic']}")
        if response.status_code != 404:
            response.raise_for_status()


class PgLockDriver:
    """Mantém uma transação aberta segurando ACCESS EXCLUSIVE na tabela."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._connection: psycopg.Connection | None = None
        self._lock = threading.Lock()

    def enable(self, params: dict) -> None:
        with self._lock:
            if self._connection is not None:
                return
            connection = psycopg.connect(self._dsn, application_name=params["application_name"], connect_timeout=3)
            try:
                connection.execute(
                    sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier(params["table"]))
                )
            except Exception:
                connection.close()
                raise
            self._connection = connection

    def disable(self, params: dict) -> None:
        with self._lock:
            if self._connection is None:
                return
            try:
                self._connection.rollback()
            finally:
                self._connection.close()
                self._connection = None


class CpuBurnDriver:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def enable(self, params: dict) -> None:
        self._client.post("/internal/cpu-burn", json={"enabled": True, "workers": params.get("workers", 2)}).raise_for_status()

    def disable(self, params: dict) -> None:
        self._client.post("/internal/cpu-burn", json={"enabled": False}).raise_for_status()


class DeployDriver:
    """Deploy é feito pelo host (make deploy-bad/deploy-good): o chaos-control
    não tem acesso ao Docker.
    """

    def enable(self, params: dict) -> None:
        raise ManualActionRequired(params["enable_command"])

    def disable(self, params: dict) -> None:
        raise ManualActionRequired(params["disable_command"])


class FaultFlagDriver:
    """Liga/desliga uma flag de falha num serviço, pela porta interna dele
    (fora da telemetria). target escolhe shop-api (POST /faults/{flag}) ou
    payment-service (POST /internal/faults/{flag}).
    """

    def __init__(self, clients: dict[str, httpx.Client]) -> None:
        self._clients = clients
        self._paths = {"shop": "/faults", "payment": "/internal/faults"}

    def _post(self, params: dict, enabled: bool) -> None:
        target = params["target"]
        path = f"{self._paths[target]}/{params['flag']}"
        self._clients[target].post(path, json={"enabled": enabled, "config": params.get("config", {})}).raise_for_status()

    def enable(self, params: dict) -> None:
        self._post(params, True)

    def disable(self, params: dict) -> None:
        self._post(params, False)


class PgIndexDriver:
    """Deixa um índice INVALID, o estado de um REINDEX/CREATE INDEX
    CONCURRENTLY interrompido: o planner o ignora e as consultas viram seq
    scan, mas as escritas continuam mantendo o índice. Por isso o disable é
    instantâneo, sem os ~20 s de rebuild de um DROP/CREATE. Exige
    superusuário (UPDATE em pg_index).
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _set_valid(self, index: str, valid: bool) -> None:
        with psycopg.connect(self._dsn, application_name="inventory-maintenance", connect_timeout=3, autocommit=True) as conn:
            conn.execute("UPDATE pg_index SET indisvalid = %s WHERE indexrelid = %s::regclass", (valid, index))

    def enable(self, params: dict) -> None:
        self._set_valid(params["index"], False)

    def disable(self, params: dict) -> None:
        self._set_valid(params["index"], True)


class CompositeDriver:
    """Combina vários drivers num cenário só. Liga na ordem dada e desliga na
    ordem inversa, para que o cleanup espelhe a montagem.
    """

    def __init__(self, drivers: dict[str, "Driver"]) -> None:
        self._drivers = drivers

    def enable(self, params: dict) -> None:
        applied: list[dict] = []
        try:
            for step in params["steps"]:
                self._drivers[step["driver"]].enable(step.get("params", {}))
                applied.append(step)
        except Exception:
            for step in reversed(applied):
                try:
                    self._drivers[step["driver"]].disable(step.get("params", {}))
                except Exception:
                    logger.exception("rollback do passo %s falhou", step["driver"])
            raise

    def disable(self, params: dict) -> None:
        for step in reversed(params["steps"]):
            self._drivers[step["driver"]].disable(step.get("params", {}))
