"""Create a dependency graph for The Last Coffee Ceremony (no model calls)."""
from pathlib import Path
from ai_content.db import Database
from ai_content.orchestrator import Orchestrator

ROOT = Path(__file__).resolve().parents[1]
STORYBOARD = ROOT / "examples" / "storyboard.example.json"
DB_PATH = ROOT / "outputs" / "system.db"

orch = Orchestrator(Database(DB_PATH))
project_id = orch.register_project(STORYBOARD)
run_id = orch.create_run(project_id, {
    "film_language": "am",
    "subtitle_language": "en",
    "concept": "The Last Coffee Ceremony",
    "execution_mode": "animatic_first",
})

# Create the jobs in topological order. The worker implementations arrive in later phases.
refs_job, _ = orch.add_job(
    run_id, stage="character_references", inputs={"character_bible": "storyboard.characters"},
    model="image-adapter", model_version="pending",
)
keyframe_jobs = []
narration_jobs = []
import json
storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
for shot in storyboard["shots"]:
    keyframe_id, _ = orch.add_job(
        run_id, stage="keyframe", subject_id=shot["id"],
        inputs={"image_prompt": shot["image_prompt"], "character_ids": shot["characters"]},
        model="image-adapter", model_version="pending", dependencies=[refs_job],
    )
    keyframe_jobs.append(keyframe_id)
    narration_id, _ = orch.add_job(
        run_id, stage="narration", subject_id=shot["id"],
        inputs={"text": shot["narration"]["text"],
                "lang": "am", "subtitle_text": shot["narration"]["subtitle_text"],
                "subtitle_language": "en"},
        model="tts-adapter", model_version="pending",
    )
    narration_jobs.append(narration_id)

music_job, _ = orch.add_job(
    run_id, stage="music", inputs={"prompt": storyboard["music"]["prompt"],
                                    "duration_s": storyboard["music"]["duration_s"]},
    model="music-adapter", model_version="pending",
)
all_dependencies = keyframe_jobs + narration_jobs + [music_job]
orch.add_job(run_id, stage="animatic_assembly", inputs={"aspect_ratios": ["16:9", "9:16"],
             "fps": 24, "resolution": "1080p"}, dependencies=all_dependencies)
orch.start_run(run_id)
print(f"Project: {project_id}")
print(f"Run:     {run_id}")
print(f"SQLite:  {DB_PATH}")
print("The graph is queued; no paid API or GPU calls have been made.")
