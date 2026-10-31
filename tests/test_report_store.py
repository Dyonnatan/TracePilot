import agents.report_store as report_store


def test_save_load_and_list_newest_first(reports_dir):
    report_store.save("older", {"id": "older", "created_at": 1, "status": "done"})
    report_store.save("newer", {"id": "newer", "created_at": 2, "status": "running"})

    loaded = report_store.load("older")
    assert loaded["id"] == "older"
    assert loaded["status"] == "done"
    assert "updated_at" in loaded

    assert report_store.load("missing") is None
    assert [item["id"] for item in report_store.list_all()] == ["newer", "older"]


def test_list_skips_invalid_json(reports_dir):
    (reports_dir / "broken.json").write_text("{", encoding="utf-8")
    report_store.save("ok", {"id": "ok", "created_at": 1})

    assert [item["id"] for item in report_store.list_all()] == ["ok"]
