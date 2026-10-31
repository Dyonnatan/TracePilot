import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from drivers import DeployDriver, ToxiproxyDriver
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

    drivers = {name: FakeDriver() for name in ("toxiproxy", "pg_lock", "cpu_burn")}
    drivers["deploy"] = DeployDriver()
    test_runner = ScenarioRunner(scenarios, drivers, timer_factory=timer_factory, clock=lambda: 1000.0)
    test_runner.timers = timers
    test_runner.fake_drivers = drivers
    return test_runner


def test_catalog_has_four_distinct_categories(scenarios):
    assert set(scenarios) == {"payment_latency", "cpu_saturation", "db_lock", "coupon_bug"}
    assert len({scenario["category"] for scenario in scenarios.values()}) == 4
    assert scenarios["payment_latency"]["pitch_role"] == "protagonist"


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


@pytest.fixture
def api(runner):
    main.app.state.runner = runner
    with TestClient(main.app) as test_client:
        yield test_client
    del main.app.state.runner


def test_api_lists_and_toggles(api):
    assert len(api.get("/api/scenarios").json()) == 4
    assert api.post("/api/scenarios/payment_latency/enable").json()["active"] is True
    assert api.post("/api/scenarios/payment_latency/disable").json()["active"] is False


def test_api_deploy_requires_manual_action(api):
    response = api.post("/api/scenarios/coupon_bug/enable")
    assert response.status_code == 409
    assert "make deploy-bad" in response.json()["detail"]


def test_api_unknown_scenario(api):
    assert api.post("/api/scenarios/nope/enable").status_code == 404
