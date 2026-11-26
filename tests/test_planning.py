import json
from pathlib import Path

import pytest

from ai_content.db import Database
from ai_content.planning import DraftService, MockPlanner, PlanningError


def test_mock_planner_creates_valid_amharic_english_draft(tmp_path):
    service = DraftService(Database(tmp_path / "db.sqlite"))
    draft = service.create_draft("A family gathers for coffee.")
    assert draft["status"] == "pending_approval"
    assert draft["payload"]["language"] == "am"
    assert draft["payload"]["subtitle_language"] == "en"
    assert len(draft["payload"]["shots"]) == 8
    assert all(s["narration"]["lang"] == "am" for s in draft["payload"]["shots"])
    assert all(s["narration"]["subtitle_text"] for s in draft["payload"]["shots"])
    assert "[English subtitle draft]" not in json.dumps(draft["payload"], ensure_ascii=False)


def test_draft_is_not_a_project_until_human_approval(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    service = DraftService(db)
    draft = service.create_draft("A family gathers for coffee.")
    assert db.execute("SELECT id FROM projects") == []
    assert db.execute("SELECT id FROM jobs") == []
    project_id, path = service.approve(draft["id"], tmp_path / "approved" / "storyboard.json")
    assert path.is_file()
    assert db.execute("SELECT id FROM projects")[0]["id"] == project_id
    assert db.execute("SELECT id FROM jobs") == []
    assert service.get_draft(draft["id"])["status"] == "approved"


def test_cannot_approve_same_draft_twice(tmp_path):
    service = DraftService(Database(tmp_path / "db.sqlite"))
    draft = service.create_draft("A family gathers for coffee.")
    service.approve(draft["id"], tmp_path / "one.json")
    with pytest.raises(PlanningError):
        service.approve(draft["id"], tmp_path / "two.json")


def test_rejection_requires_reason_and_blocks_approval(tmp_path):
    service = DraftService(Database(tmp_path / "db.sqlite"))
    draft = service.create_draft("A family gathers for coffee.")
    with pytest.raises(ValueError):
        service.reject(draft["id"], " ")
    service.reject(draft["id"], "Needs cultural review")
    with pytest.raises(PlanningError):
        service.approve(draft["id"], tmp_path / "approved.json")
    assert service.get_draft(draft["id"])["status"] == "rejected"


class AlwaysInvalidPlanner(MockPlanner):
    name = "invalid-test-planner"

    def plan(self, idea, *, title, language, subtitle_language):
        return {"title": title}

    def repair(self, storyboard, issues, *, idea):
        return storyboard


def test_repair_loop_is_bounded_and_invalid_draft_needs_revision(tmp_path):
    service = DraftService(Database(tmp_path / "db.sqlite"), planner=AlwaysInvalidPlanner(), max_repairs=2)
    draft = service.create_draft("Test idea")
    assert draft["status"] == "needs_revision"
    assert draft["repair_attempts"] == 2
    assert draft["issues"]
    with pytest.raises(PlanningError):
        service.approve(draft["id"], tmp_path / "should_not_exist.json")


def test_repair_limit_is_capped():
    with pytest.raises(ValueError):
        DraftService(Database(":memory:"), max_repairs=6)
