import json
from pathlib import Path

from ai_content.db import Database
from ai_content.orchestrator import Orchestrator
from ai_content.visual import MockSVGProvider, VisualProductionService


def setup_project(tmp_path):
    source = Path(__file__).parents[1] / "examples" / "storyboard.example.json"
    storyboard = tmp_path / "storyboard.json"
    storyboard.write_bytes(source.read_bytes())
    db = Database(tmp_path / "system.db")
    project_id = Orchestrator(db).register_project(storyboard)
    return db, project_id


def test_phase3_generates_character_refs_and_keyframes(tmp_path):
    db, project_id = setup_project(tmp_path)
    result = VisualProductionService(db).generate(project_id, tmp_path / "visuals", width=512, height=288)
    assert result["run_status"] == "succeeded"
    assert result["preview_only"] is True
    assert len(result["generated_this_run"]) == 10  # 2 character refs + 8 shots
    assert all(Path(p).is_file() for p in result["generated_this_run"])
    assert len([a for a in result["artifacts"] if a["stage"] == "shot_keyframe"]) == 8
    assert Path(result["manifest_path"]).is_file()


def test_phase3_records_hashes_and_prompt_sidecars(tmp_path):
    db, project_id = setup_project(tmp_path)
    result = VisualProductionService(db).generate(project_id, tmp_path / "visuals", width=512, height=288)
    for artifact in result["artifacts"]:
        assert len(artifact["content_hash"]) == 64
        sidecar = Path(artifact["path"]).with_suffix(".prompt.json")
        assert sidecar.is_file()
        prompt_data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert prompt_data["provider"] == MockSVGProvider.name


def test_phase3_cache_reuses_identical_assets(tmp_path):
    db, project_id = setup_project(tmp_path)
    service = VisualProductionService(db)
    first = service.generate(project_id, tmp_path / "visuals", width=512, height=288)
    second = service.generate(project_id, tmp_path / "visuals", width=512, height=288)
    assert len(first["generated_this_run"]) == 10
    assert second["generated_this_run"] == []
    assert len(second["cache_reused_subjects"]) == 10


def test_provider_contract_is_replaceable(tmp_path):
    class RecordingProvider:
        name = "test-provider"
        version = "test-1"
        def __init__(self): self.calls = []
        def generate(self, **kwargs):
            self.calls.append(kwargs)
            kwargs["output_path"].write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
    db, project_id = setup_project(tmp_path)
    provider = RecordingProvider()
    result = VisualProductionService(db, provider=provider).generate(project_id, tmp_path / "visuals", width=512, height=288)
    assert result["run_status"] == "succeeded"
    assert len(provider.calls) == 10
    assert result["preview_only"] is False


def test_storyboard_path_survives_moving_entire_project_folder(tmp_path):
    import shutil

    source = Path(__file__).parents[1] / "examples" / "storyboard.example.json"
    project_root = tmp_path / "workspace" / "ai_content_system"
    project_root.mkdir(parents=True)
    db = Database(project_root / "outputs" / "system.db")
    project_id = Orchestrator(db).register_project(source)

    stored = db.execute("SELECT storyboard_path FROM projects WHERE id=?", (project_id,))[0][0]
    assert not Path(stored).is_absolute()
    assert (project_root / stored).is_file()

    moved_root = tmp_path / "moved" / "ai_content_system"
    moved_root.parent.mkdir(parents=True)
    shutil.move(str(project_root), str(moved_root))
    moved_db = Database(moved_root / "outputs" / "system.db")
    result = VisualProductionService(moved_db).generate(
        project_id, moved_root / "outputs" / "visuals", width=512, height=288)
    assert result["run_status"] == "succeeded"
    assert len(result["generated_this_run"]) == 10
