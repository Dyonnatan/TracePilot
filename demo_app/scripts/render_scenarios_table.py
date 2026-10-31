"""Regenera a tabela de cenários do README a partir de scenarios/*.yaml
(a fonte da verdade). Uso: make scenarios-table
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
START, END = "<!-- scenarios:start -->", "<!-- scenarios:end -->"

def cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render() -> str:
    rows = [
        "| Cenário | Categoria | Como ativar | TTL | Sintoma do usuário | Causa raiz (gabarito) |",
        "|---|---|---|---|---|---|",
    ]
    for path in sorted((ROOT / "scenarios").glob("*.yaml")):
        scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
        activation = scenario["activation"]
        if activation["driver"] == "deploy":
            how = f"`{activation['params']['enable_command']}`"
        else:
            how = "Painel chaos-control"
        ttl = f"{scenario['ttl_seconds']} s" if scenario.get("ttl_seconds") else "manual"
        name = f"`{scenario['name']}`" + (" (protagonista)" if scenario.get("pitch_role") == "protagonist" else "")
        rows.append(
            f"| {name} | {scenario['category']} | {how} | {ttl} | "
            f"{cell(scenario['user_symptom'])} | {cell(scenario['root_cause'])} |"
        )
    return "\n".join(rows)


def main() -> None:
    content = README.read_text(encoding="utf-8")
    pattern = re.compile(f"{re.escape(START)}.*?{re.escape(END)}", re.DOTALL)
    if not pattern.search(content):
        sys.exit(f"marcadores {START} / {END} não encontrados em {README}")
    README.write_text(pattern.sub(f"{START}\n{render()}\n{END}", content), encoding="utf-8")


if __name__ == "__main__":
    main()
