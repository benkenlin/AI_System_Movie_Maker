import json
from pathlib import Path
import pytest
from ai_content.db import Database
from ai_content.hashing import artifact_key, sha256_json, sha256_file
from ai_content.orchestrator import Orchestrator, OrchestratorError

EXAMPLE = Path(__file__).parents[1] / "examples" / "storyboard.example.json"

def setup(tmp_path):
    orch = Orchestrator(Database(tmp_path / "db" / "system.db"))
    project = orch.register_project(EXAMPLE)
    run = orch.create_run(project, {"film_language": "am", "subtitle_language": "en"})
    orch.start_run(run)
    return orch, project, run

def test_hash_is_independent_of_dict_order():
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})

def test_artifact_key_changes_when_model_or_input_changes():
    base = artifact_key(stage="narration", inputs={"text": "hello"}, model="tts", model_version="1")
    changed_input = artifact_key(stage="narration", inputs={"text": "hello!"}, model="tts", model_version="1")
    changed_model = artifact_key(stage="narration", inputs={"text": "hello"}, model="tts", model_version="2")
    assert len(base) == 64 and base != changed_input and base != changed_model

def test_project_registration_validates_storyboard(tmp_path):
    orch = Orchestrator(Database(tmp_path / "db.sqlite"))
    bad = tmp_path / "bad.json"
    bad.write_text('{"title": "incomplete"}', encoding="utf-8")
    with pytest.raises(Exception):
        orch.register_project(bad)

def test_dependencies_block_downstream_until_parent_succeeds(tmp_path):
    orch, _, run = setup(tmp_path)
    first, _ = orch.add_job(run, stage="keyframe", subject_id="s01", inputs={"prompt": "x"})
    second, _ = orch.add_job(run, stage="clip", subject_id="s01", inputs={"motion": "y"}, dependencies=[first])
    claimed = orch.claim_ready_job(run, "worker-a")
    assert claimed["id"] == first
    assert orch.claim_ready_job(run, "worker-b") is None
    artifact = tmp_path / "keyframe.txt"
    artifact.write_text("fake keyframe bytes", encoding="utf-8")
    orch.complete_job(first, artifact_path=artifact, media_type="text/plain")
    assert orch.claim_ready_job(run, "worker-b")["id"] == second

def test_successful_artifact_is_reused_on_later_run(tmp_path):
    orch, project, run = setup(tmp_path)
    job, cache = orch.add_job(run, stage="narration", subject_id="s01", inputs={"text": "Selam"}, model="tts", model_version="v1")
    assert cache is False
    assert orch.claim_ready_job(run, "worker")["id"] == job
    output = tmp_path / "voice.wav"
    output.write_bytes(b"audio payload")
    expected_content_hash = sha256_file(output)
    orch.complete_job(job, artifact_path=output, media_type="audio/wav")
    run2 = orch.create_run(project)
    orch.start_run(run2)
    cached_job, cache = orch.add_job(run2, stage="narration", subject_id="s01", inputs={"text": "Selam"}, model="tts", model_version="v1")
    assert cache is True
    assert orch.claim_ready_job(run2, "worker") is None
    rows = orch.db.execute("SELECT content_hash FROM artifacts WHERE project_id=?", (project,))
    assert rows[0]["content_hash"] == expected_content_hash

def test_retry_budget_is_bounded(tmp_path):
    orch, _, run = setup(tmp_path)
    job, _ = orch.add_job(run, stage="video", inputs={"shot": "s01"}, max_attempts=1)
    orch.claim_ready_job(run, "gpu-worker")
    assert orch.fail_job(job, "GPU out of memory") == "failed"

def test_event_export_is_jsonl(tmp_path):
    orch, _, run = setup(tmp_path)
    target = orch.export_events_jsonl(run, tmp_path / "runs.jsonl")
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2
    assert json.loads(lines[0])["event_type"] == "run_created"

def test_failed_dependency_marks_descendants_stale(tmp_path):
    orch, _, run = setup(tmp_path)
    parent, _ = orch.add_job(run, stage="keyframe", subject_id="s01", inputs={"p": "bad"}, max_attempts=1)
    child, _ = orch.add_job(run, stage="clip", subject_id="s01", inputs={"m": "move"}, dependencies=[parent])
    orch.claim_ready_job(run, "worker")
    orch.fail_job(parent, "generation failed", retry=False)
    assert orch.finish_run_if_complete(run) == "failed"
    rows = orch.db.execute("SELECT id,status FROM jobs WHERE run_id=?", (run,))
    assert {r["id"]: r["status"] for r in rows}[child] == "stale"
