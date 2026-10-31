"""Carrega o catálogo de cenários de demo_app/scenarios/*.yaml."""
from pathlib import Path

import yaml

REQUIRED_KEYS = {"name", "title", "category", "culprit_component", "activation", "root_cause", "expected_signals"}


class InvalidScenario(ValueError):
    pass


def load_scenarios(directory: Path) -> dict[str, dict]:
    scenarios = {}
    for path in sorted(directory.glob("*.yaml")):
        scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
        missing = REQUIRED_KEYS - scenario.keys()
        if missing:
            raise InvalidScenario(f"{path.name}: faltam chaves {sorted(missing)}")
        if scenario["name"] != path.stem:
            raise InvalidScenario(f"{path.name}: name '{scenario['name']}' difere do nome do arquivo")
        if "driver" not in scenario["activation"]:
            raise InvalidScenario(f"{path.name}: activation.driver ausente")
        scenarios[scenario["name"]] = scenario
    return scenarios
