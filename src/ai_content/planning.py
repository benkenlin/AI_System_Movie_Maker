"""Provider-neutral story planning, critique, repair and human approval."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from .db import Database
from .hashing import sha256_json
from .models import Storyboard
from .orchestrator import Orchestrator


class Planner(Protocol):
    """An adapter that turns a film idea into a storyboard-shaped dictionary."""

    name: str

    def plan(self, idea: str, *, title: str, language: str,
             subtitle_language: str) -> dict[str, Any]: ...

    def repair(self, storyboard: dict[str, Any], issues: list[str], *,
               idea: str) -> dict[str, Any]: ...


class MockPlanner:
    """Deterministic offline planner used for development and tests."""

    name = "mock-template-v1"

    def plan(self, idea: str, *, title: str, language: str,
             subtitle_language: str) -> dict[str, Any]:
        beats = [
            ("Establish the quiet morning and the home where the ceremony begins.", "Dawn light enters the home; dust floats in a warm beam.", "ጥዋቱ በተለመደው ጸጥታ ይጀምራል።", "The morning begins in familiar quiet."),
            ("Introduce the elder preparing the coffee tools.", "Close view of hands arranging the jebena, cups and tray.", "እያንዳንዱ ዕቃ ቦታው አለው፤ እያንዳንዱም እንቅስቃሴ ትርጉም አለው።", "Every object has its place, and every movement has meaning."),
            ("Show the washing and roasting of the green coffee beans.", "Beans are washed, then stirred in a shallow roasting pan.", "አረንጓዴዎቹ የቡና ፍሬዎች ታጥበው በእሳት ላይ ቀስ በቀስ ይቆላሉ።", "The green coffee beans are washed and slowly roasted over the fire."),
            ("Reveal the aroma as the roasted beans are shared with guests.", "The roaster lifts the pan; guests lean in to appreciate the aroma.", "መዓዛው ቤቱን ሞልቶ ሁሉንም ወደ አንድነት ይሰበስባል።", "The aroma fills the room and draws everyone together."),
            ("Show water heating in the jebena while guests settle together.", "Steam rises from the clay pot as guests sit in a circle.", "በጀበናው ውስጥ ውሃው ሲሞቅ፣ ወሬና ታሪኮች ይጀምራሉ።", "As the water warms in the jebena, stories begin to flow."),
            ("Pour the first cup carefully and offer it to a guest.", "A thin stream of coffee fills a small cup; it is offered respectfully.", "የመጀመሪያው ሲኒ በጥንቃቄና በአክብሮት ይቀርባል።", "The first cup is served with care and respect."),
            ("Let conversation and connection become the emotional centre.", "Faces listen and smile; hands pass cups around the circle.", "ለአፍታ ሁሉም ቤተሰብ በአንድ ጠረጴዛ ዙሪያ አንድ ታሪክ ይጋራል።", "For a moment, the family shares one table and one story."),
            ("End on the coffee set and the gathering continuing in warmth.", "The camera gently pulls back from the cups and glowing room.", "ሥነ ሥርዓቱ ይጠናቀቃል፤ የፈጠረው ትስስር ግን ይቀጥላል።", "The ceremony ends, but the bond it creates remains.")
        ]
        shots = []
        for index, (beat, visual, narration, subtitle) in enumerate(beats, start=1):
            shots.append({
                "id": f"s{index:02d}", "duration_s": 7 if index < 8 else 13,
                "image_prompt": f"Cinematic, respectful Ethiopian coffee ceremony scene. {visual} Story beat: {beat} Natural warm light, realistic details, consistent fictional characters, no text.",
                "motion_prompt": "Slow, stable cinematic camera movement; subtle natural gestures; preserve character and prop continuity.",
                "characters": ["host", "guests"], "vertical_crop_x": 0.5, "camera": "push_in",
                "subtitle_en": subtitle,
                "narration": {"text": narration, "lang": language,
                              "subtitle_text": subtitle, "lexicon": {}},
                "transition": "crossfade" if index in (1, 8) else "cut"
            })
        return {
            "schema_version": "1.0", "storyboard_version": 1,
            "title": title,
            "language": language,
            "subtitle_language": subtitle_language,
            "target_runtime_s": 62, "shot_count": 8,
            "aspect_ratios": ["16:9", "9:16"],
            "style": {"block": "Cinematic naturalistic Ethiopian home interior, warm dawn light, restrained earthy palette."},
            "narration_voice": {"model": "gemini-tts", "voice": "Kore"},
            "subtitle_language": subtitle_language,
            "logline": f"A quiet gathering around an Ethiopian coffee ceremony reveals how ritual, memory and hospitality connect generations. Inspired by: {idea[:250]}",
            "ai_disclosure": {"in_film": True, "end_card_text": "Some visuals and/or audio in this film were created with AI tools."},
            "characters": {
                "host": {"descriptor": "A fictional Ethiopian elder hosting a traditional coffee ceremony, wearing modest culturally appropriate clothing; warm, calm and attentive.", "origin": "fictional"},
                "guests": {"descriptor": "A small group of fictional family members and neighbours of varied adult ages, seated respectfully together during the ceremony.", "origin": "fictional"}
            },
            "music": {"prompt": "Gentle, warm instrumental underscore with restrained Ethiopian-inspired acoustic textures; avoid imitating a specific living artist or copyrighted recording.", "instrumental": True, "duration_s": 69, "candidates": [], "selected": None, "rationale": ""},
            "shots": shots
        }

    def repair(self, storyboard: dict[str, Any], issues: list[str], *,
               idea: str) -> dict[str, Any]:
        # The offline adapter deliberately does not invent fixes for arbitrary errors.
        # It returns the draft unchanged; production adapters can use issues to revise.
        return storyboard


@dataclass
class Critique:
    passed: bool
    issues: list[str]


class StoryCritic:
    """Validate the schema and enforce project-specific planning requirements."""

    def review(self, payload: dict[str, Any], *, language: str,
               subtitle_language: str) -> Critique:
        issues: list[str] = []
        try:
            storyboard = Storyboard.model_validate(payload)
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"]) or "<root>"
                issues.append(f"{location}: {error['msg']}")
            return Critique(False, issues)
        if storyboard.language != language:
            issues.append(f"language must be {language!r}")
        if storyboard.subtitle_language != subtitle_language:
            issues.append(f"subtitle_language must be {subtitle_language!r}")
        for shot in storyboard.shots:
            if not shot.subtitle_en.strip():
                issues.append(f"{shot.id}.subtitle_en is required")
            style_block=storyboard.style.block.strip().casefold()
            if len(style_block)>=20 and style_block in shot.image_prompt.casefold():
                issues.append(f"{shot.id}.image_prompt repeats the shared style block; style is injected by the pipeline")
            if shot.narration.lang != language:
                issues.append(f"{shot.id}.narration.lang must be {language!r}")
        return Critique(not issues, issues)


class PlanningError(RuntimeError):
    pass


class DraftService:
    def __init__(self, database: Database, planner: Planner | None = None,
                 critic: StoryCritic | None = None, max_repairs: int = 2):
        if max_repairs < 0 or max_repairs > 5:
            raise ValueError("max_repairs must be between 0 and 5")
        self.db = database
        self.planner = planner or MockPlanner()
        self.critic = critic or StoryCritic()
        self.max_repairs = max_repairs

    def create_draft(self, idea: str, *, title: str = "The Last Coffee Ceremony",
                     language: str = "am", subtitle_language: str = "en") -> dict[str, Any]:
        if not idea.strip():
            raise ValueError("Film idea must not be empty")
        payload = self.planner.plan(idea.strip(), title=title,
                                    language=language, subtitle_language=subtitle_language)
        critique = self.critic.review(payload, language=language,
                                      subtitle_language=subtitle_language)
        attempts = 0
        while not critique.passed and attempts < self.max_repairs:
            attempts += 1
            payload = self.planner.repair(payload, critique.issues, idea=idea)
            critique = self.critic.review(payload, language=language,
                                          subtitle_language=subtitle_language)
        draft_id = str(uuid.uuid4())
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        status = "pending_approval" if critique.passed else "needs_revision"
        with self.db.transaction() as con:
            con.execute("""INSERT INTO storyboard_drafts
                (id,title,idea,payload_json,payload_hash,planner,status,repair_attempts,issues_json)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (draft_id, title, idea, payload_json, sha256_json(payload), self.planner.name,
                 status, attempts, json.dumps(critique.issues, ensure_ascii=False)))
            con.execute("INSERT INTO events(run_id,job_id,event_type,details_json) VALUES(NULL,NULL,?,?)",
                        ("storyboard_draft_created", json.dumps({"draft_id": draft_id,
                         "status": status, "planner": self.planner.name,
                         "repair_attempts": attempts, "issues": critique.issues}, ensure_ascii=False)))
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        rows = self.db.execute("SELECT * FROM storyboard_drafts WHERE id=?", (draft_id,))
        if not rows:
            raise PlanningError(f"Unknown storyboard draft: {draft_id}")
        row = dict(rows[0])
        row["payload"] = json.loads(row.pop("payload_json"))
        row["issues"] = json.loads(row.pop("issues_json"))
        return row

    def approve(self, draft_id: str, destination: str | Path) -> tuple[str, Path]:
        draft = self.get_draft(draft_id)
        if draft["status"] != "pending_approval":
            raise PlanningError(f"Draft cannot be approved from status {draft['status']!r}")
        # Revalidate immediately before crossing the human approval boundary.
        Storyboard.model_validate(draft["payload"])
        path = Path(destination).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(draft["payload"], ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        project_id = Orchestrator(self.db).register_project(path)
        with self.db.transaction() as con:
            cur = con.execute("""UPDATE storyboard_drafts SET status='approved',
                approved_project_id=?,approved_path=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id=? AND status='pending_approval'""", (project_id, str(path), draft_id))
            if cur.rowcount != 1:
                raise PlanningError("Draft approval state changed; reload and review it")
            con.execute("INSERT INTO events(run_id,job_id,event_type,details_json) VALUES(NULL,NULL,?,?)",
                        ("storyboard_draft_approved", json.dumps({"draft_id": draft_id,
                         "project_id": project_id, "path": str(path)})))
        return project_id, path

    def reject(self, draft_id: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("A rejection reason is required")
        with self.db.transaction() as con:
            cur = con.execute("""UPDATE storyboard_drafts SET status='rejected',
                rejection_reason=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id=? AND status='pending_approval'""", (reason.strip(), draft_id))
            if cur.rowcount != 1:
                raise PlanningError("Draft is unknown or is not awaiting approval")
            con.execute("INSERT INTO events(run_id,job_id,event_type,details_json) VALUES(NULL,NULL,?,?)",
                        ("storyboard_draft_rejected", json.dumps({"draft_id": draft_id,
                         "reason": reason.strip()}, ensure_ascii=False)))
