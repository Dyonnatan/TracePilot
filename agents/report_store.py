"""Persistência de investigações em `reports/` — cada investigação vira um
arquivo JSON com metadados (id, status, timestamps) + o estado final
completo do grafo, para a interface web listar, acompanhar progresso e
permitir drill-down na evidência bruta sem precisar rodar de novo.

Decisão de design: arquivo JSON simples em vez de banco de dados — MVP de
hackathon, volume baixo, sem concorrência pesada de escrita. Se o volume de
investigações crescer, trocar por SQLite é o próximo passo natural (mesma
pasta `reports/`, outro backend).
"""
import json
import time
import uuid
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def new_investigation_id() -> str:
    return uuid.uuid4().hex[:12]


def _path(investigation_id: str) -> Path:
    return REPORTS_DIR / f"{investigation_id}.json"


def save(investigation_id: str, record: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    record["updated_at"] = time.time()
    _path(investigation_id).write_text(
        json.dumps(record, default=str, ensure_ascii=False, indent=2)
    )


def load(investigation_id: str) -> dict | None:
    path = _path(investigation_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_all() -> list[dict]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for path in REPORTS_DIR.glob("*.json"):
        try:
            records.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    records.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return records
