"""Drivers que aplicam e removem cada tipo de falha. Nenhum deles passa
pelos serviços instrumentados de forma visível na telemetria.
"""
import threading
from typing import Protocol

import httpx
import psycopg
from psycopg import sql


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
