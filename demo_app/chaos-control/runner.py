"""Liga/desliga cenários com TTL: toda falha desliga sozinha ao expirar."""
import logging
import threading
import time
from collections.abc import Callable

from drivers import Driver

DEFAULT_TTL_SECONDS = 120

logger = logging.getLogger("chaos")


class UnknownScenario(KeyError):
    pass


class ScenarioRunner:
    def __init__(
        self,
        scenarios: dict[str, dict],
        drivers: dict[str, Driver],
        timer_factory: Callable[[float, Callable[[], None]], threading.Timer] = threading.Timer,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._scenarios = scenarios
        self._drivers = drivers
        self._timer_factory = timer_factory
        self._clock = clock
        self._active: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _scenario(self, name: str) -> dict:
        if name not in self._scenarios:
            raise UnknownScenario(name)
        return self._scenarios[name]

    def _driver(self, scenario: dict) -> Driver:
        return self._drivers[scenario["activation"]["driver"]]

    def status(self) -> list[dict]:
        with self._lock:
            return [self._describe(scenario) for scenario in self._scenarios.values()]

    def _describe(self, scenario: dict) -> dict:
        active = self._active.get(scenario["name"])
        return {
            "name": scenario["name"],
            "title": scenario["title"],
            "category": scenario["category"],
            "pitch_role": scenario.get("pitch_role"),
            "driver": scenario["activation"]["driver"],
            "params": scenario["activation"].get("params", {}),
            "ttl_seconds": scenario.get("ttl_seconds", DEFAULT_TTL_SECONDS),
            "user_symptom": scenario.get("user_symptom", ""),
            "root_cause": scenario["root_cause"],
            "active": active is not None,
            "enabled_at": active["enabled_at"] if active else None,
            "expires_at": active["expires_at"] if active else None,
        }

    def enable(self, name: str, ttl_seconds: int | None = None) -> dict:
        with self._lock:
            scenario = self._scenario(name)
            ttl = ttl_seconds or scenario.get("ttl_seconds") or DEFAULT_TTL_SECONDS
            self._cancel_timer(name)
            self._driver(scenario).enable(scenario["activation"].get("params", {}))

            activation_id = object()
            timer = self._timer_factory(ttl, lambda: self._expire(name, activation_id))
            timer.daemon = True
            timer.start()
            now = self._clock()
            self._active[name] = {"id": activation_id, "timer": timer, "enabled_at": now, "expires_at": now + ttl}
            logger.info("cenário %s ligado por %ss", name, ttl)
            return self._describe(scenario)

    def disable(self, name: str) -> dict:
        with self._lock:
            scenario = self._scenario(name)
            self._cancel_timer(name)
            self._driver(scenario).disable(scenario["activation"].get("params", {}))
            self._active.pop(name, None)
            logger.info("cenário %s desligado", name)
            return self._describe(scenario)

    def _expire(self, name: str, activation_id: object) -> None:
        with self._lock:
            active = self._active.get(name)
            # Um enable posterior substituiu esta ativação: o timer antigo não vale mais.
            if active is None or active["id"] is not activation_id:
                return
            try:
                self.disable(name)
            except Exception:
                logger.exception("falha ao expirar cenário %s", name)

    def _cancel_timer(self, name: str) -> None:
        active = self._active.get(name)
        if active:
            active["timer"].cancel()

    def reset_all(self) -> None:
        """Remove qualquer falha remanescente (ex.: após restart do chaos-control)."""
        for name, scenario in self._scenarios.items():
            if scenario["activation"]["driver"] == "deploy":
                continue
            try:
                self.disable(name)
            except Exception as exc:
                logger.warning("reset de %s falhou: %s", name, exc)
