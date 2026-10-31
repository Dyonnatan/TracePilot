import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from drivers import CompositeDriver, DeployDriver, FaultFlagDriver, PgIndexDriver, ToxiproxyDriver
from runner import ScenarioRunner, UnknownScenario
from scenarios import InvalidScenario, load_scenarios

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"


class FakeDriver:
    def __init__(self):
        self.calls = []

    def enable(self, params):
        self.calls.append(("enable", params))

    def disable(self, params):
        self.calls.append(("disable", params))


class FakeTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.cancelled = False
        self.daemon = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.callback()


@pytest.fixture
def scenarios():
    return load_scenarios(SCENARIOS_DIR)


@pytest.fixture
def runner(scenarios):
    timers = []

    def timer_factory(interval, callback):
        timer = FakeTimer(interval, callback)
        timers.append(timer)
        return timer

    drivers = {name: FakeDriver() for name in ("toxiproxy", "pg_lock", "cpu_burn", "fault_flag", "pg_index")}
    drivers["deploy"] = DeployDriver()
    drivers["composite"] = CompositeDriver(drivers)
    test_runner = ScenarioRunner(scenarios, drivers, timer_factory=timer_factory, clock=lambda: 1000.0)
    test_runner.timers = timers
    test_runner.fake_drivers = drivers
    return test_runner


EXPECTED_SCENARIOS = {
    "payment_latency",
    "cpu_saturation",
    "db_lock",
    "coupon_bug",
    "payment_errors",
    "n_plus_one",
    "missing_index",
    "blocking_io",
    "memory_leak",
    "retry_storm",
    "chatty_logging",
}


def test_catalog(scenarios):
    assert set(scenarios) == EXPECTED_SCENARIOS
    assert {scenario["category"] for scenario in scenarios.values()} == {
        "network",
        "host_resource",
        "database",
        "code_change",
        "dependency",
        "performance_antipattern",
    }
    protagonists = [name for name, scenario in scenarios.items() if scenario.get("pitch_role") == "protagonist"]
    assert protagonists == ["payment_latency"]


def test_every_scenario_driver_is_registered(scenarios):
    drivers = main.build_drivers()
    for name, scenario in scenarios.items():
        activation = scenario["activation"]
        assert activation["driver"] in drivers, name
        for step in activation.get("params", {}).get("steps", []):
            assert step["driver"] in drivers, f"{name}: {step['driver']}"


def test_invalid_scenario_is_rejected(tmp_path):
    (tmp_path / "broken.yaml").write_text("name: broken\ntitle: x\n", encoding="utf-8")
    with pytest.raises(InvalidScenario):
        load_scenarios(tmp_path)


def test_enable_uses_ttl_and_expires(runner):
    state = runner.enable("payment_latency")
    assert state["active"] is True
    assert state["expires_at"] == 1120.0
    assert runner.timers[-1].interval == 120

    runner.timers[-1].fire()
    toxiproxy = runner.fake_drivers["toxiproxy"]
    assert [call[0] for call in toxiproxy.calls] == ["enable", "disable"]
    assert not any(item["active"] for item in runner.status())


def test_manual_disable_cancels_timer(runner):
    runner.enable("db_lock", ttl_seconds=30)
    timer = runner.timers[-1]
    runner.disable("db_lock")
    assert timer.cancelled
    assert timer.interval == 30


def test_stale_timer_does_not_disable_new_activation(runner):
    runner.enable("cpu_saturation")
    stale_timer = runner.timers[-1]
    runner.enable("cpu_saturation")
    stale_timer.callback()
    assert next(item for item in runner.status() if item["name"] == "cpu_saturation")["active"] is True


def test_unknown_scenario(runner):
    with pytest.raises(UnknownScenario):
        runner.enable("nope")


def test_toxiproxy_driver_creates_and_removes_toxic():
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path, request.content))
        return httpx.Response(200 if request.method == "POST" else 204)

    client = httpx.Client(base_url="http://toxiproxy", transport=httpx.MockTransport(handler))
    params = load_scenarios(SCENARIOS_DIR)["payment_latency"]["activation"]["params"]
    driver = ToxiproxyDriver(client)
    driver.enable(params)
    driver.disable(params)

    method, path, content = requests[0]
    assert (method, path) == ("POST", "/proxies/payment/toxics")
    assert json.loads(content)["attributes"] == {"latency": 1500, "jitter": 0}
    assert requests[1][:2] == ("DELETE", "/proxies/payment/toxics/payment_latency")


def test_toxiproxy_driver_ignores_missing_toxic_on_disable():
    client = httpx.Client(base_url="http://toxiproxy", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    ToxiproxyDriver(client).disable({"proxy": "payment", "toxic": "payment_latency"})


def test_fault_flag_driver_targets_each_service(scenarios):
    requests = []

    def handler(request):
        requests.append((request.url.host, request.url.path, json.loads(request.content)))
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    driver = FaultFlagDriver(
        {
            "shop": httpx.Client(base_url="http://shop-api:8081", transport=transport),
            "payment": httpx.Client(base_url="http://payment-service:8001", transport=transport),
        }
    )
    driver.enable(scenarios["payment_errors"]["activation"]["params"])
    driver.disable(scenarios["n_plus_one"]["activation"]["params"])

    assert requests == [
        ("payment-service", "/internal/faults/acquirer_failure", {"enabled": True, "config": {"rate": 0.3, "status": 503}}),
        ("shop-api", "/faults/catalog_n_plus_one", {"enabled": False, "config": {}}),
    ]


def test_fault_flag_driver_raises_on_unknown_flag():
    client = httpx.Client(base_url="http://shop-api:8081", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(httpx.HTTPStatusError):
        FaultFlagDriver({"shop": client}).enable({"target": "shop", "flag": "nope"})


def test_pg_index_driver_invalidates_and_restores_index(scenarios, monkeypatch):
    calls = []
    driver = PgIndexDriver("postgresql://unused")
    monkeypatch.setattr(driver, "_set_valid", lambda index, valid: calls.append((index, valid)))
    params = scenarios["missing_index"]["activation"]["params"]
    driver.enable(params)
    driver.disable(params)
    assert calls == [("orders_session_id_idx", False), ("orders_session_id_idx", True)]


def test_retry_storm_toggles_flag_and_latency(runner):
    runner.enable("retry_storm")
    runner.disable("retry_storm")
    flag_calls = runner.fake_drivers["fault_flag"].calls
    proxy_calls = runner.fake_drivers["toxiproxy"].calls
    assert [call[0] for call in flag_calls] == ["enable", "disable"]
    assert [call[0] for call in proxy_calls] == ["enable", "disable"]
    assert flag_calls[0][1]["flag"] == "payment_retry_no_backoff"
    assert proxy_calls[0][1]["toxic"] == "payment_retry_latency"


def test_composite_disable_order_is_reversed():
    events = []

    class Recorder:
        def __init__(self, name):
            self.name = name

        def enable(self, params):
            events.append(("enable", self.name))

        def disable(self, params):
            events.append(("disable", self.name))

    composite = CompositeDriver({"a": Recorder("a"), "b": Recorder("b")})
    params = {"steps": [{"driver": "a"}, {"driver": "b"}]}
    composite.enable(params)
    composite.disable(params)
    assert events == [("enable", "a"), ("enable", "b"), ("disable", "b"), ("disable", "a")]


def test_composite_rolls_back_applied_steps_on_failure():
    first = FakeDriver()

    class Broken:
        def enable(self, params):
            raise RuntimeError("toxiproxy fora do ar")

        def disable(self, params):
            pass

    composite = CompositeDriver({"first": first, "broken": Broken()})
    with pytest.raises(RuntimeError):
        composite.enable({"steps": [{"driver": "first"}, {"driver": "broken"}]})
    assert [call[0] for call in first.calls] == ["enable", "disable"]


@pytest.fixture
def api(runner):
    main.app.state.runner = runner
    with TestClient(main.app) as test_client:
        yield test_client
    del main.app.state.runner


def test_api_lists_and_toggles(api):
    assert len(api.get("/api/scenarios").json()) == len(EXPECTED_SCENARIOS)
    assert api.post("/api/scenarios/payment_latency/enable").json()["active"] is True
    assert api.post("/api/scenarios/payment_latency/disable").json()["active"] is False


def test_api_deploy_requires_manual_action(api):
    response = api.post("/api/scenarios/coupon_bug/enable")
    assert response.status_code == 409
    assert "make deploy-bad" in response.json()["detail"]


def test_api_unknown_scenario(api):
    assert api.post("/api/scenarios/nope/enable").status_code == 404
