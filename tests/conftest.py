import pytest

import agents.report_store as report_store


@pytest.fixture(autouse=True)
def reports_dir(tmp_path, monkeypatch):
    """Nenhum teste grava em `reports/` do repositório."""
    monkeypatch.setattr(report_store, "REPORTS_DIR", tmp_path)
    return tmp_path
