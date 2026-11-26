"""Phase 3: provider-neutral character reference and storyboard keyframe assets.

The included SVG provider creates labelled layout previews, NOT AI-generated imagery.
Replace it with an image-model adapter implementing VisualProvider for production art.
"""
from __future__ import annotations

import html
import json
import uuid
from pathlib import Path
from typing import Protocol

from .db import Database
from .hashing import artifact_key, sha256_file, sha256_json
from .models import Storyboard
from .orchestrator import Orchestrator
from .validation import load_storyboard


class VisualProvider(Protocol):
    name: str
    version: str

    def generate(self, *, prompt: str, negative_prompt: str, output_path: Path,
                 width: int, height: int, seed: int) -> None: ...


class MockSVGProvider:
    """Offline deterministic provider that renders prompt/shot preview cards as SVG."""
    name = "mock-svg-preview"
    version = "1.0"

    def generate(self, *, prompt: str, negative_prompt: str, output_path: Path,
                 width: int, height: int, seed: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        title = html.escape(prompt[:110])
        detail = html.escape(prompt[110:260])
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#30251f"/><stop offset="1" stop-color="#a66b3f"/></linearGradient></defs>
<rect width="100%" height="100%" fill="url(#bg)"/>
<circle cx="{width*0.5:.0f}" cy="{height*0.42:.0f}" r="{min(width,height)*0.16:.0f}" fill="#e8c89c" opacity=".85"/>
<rect x="{width*.16:.0f}" y="{height*.62:.0f}" width="{width*.68:.0f}" height="{height*.18:.0f}" rx="18" fill="#1c1714" opacity=".82"/>
<text x="{width*.5:.0f}" y="{height*.68:.0f}" text-anchor="middle" font-family="sans-serif" font-size="{max(14,width//38)}" fill="#fff">VISUAL DEVELOPMENT PREVIEW</text>
<text x="{width*.5:.0f}" y="{height*.74:.0f}" text-anchor="middle" font-family="sans-serif" font-size="{max(12,width//55)}" fill="#f5e7d5">{title}</text>
<text x="{width*.5:.0f}" y="{height*.79:.0f}" text-anchor="middle" font-family="sans-serif" font-size="{max(10,width//65)}" fill="#f5e7d5">{detail}</text>
</svg>'''
        output_path.write_text(svg, encoding="utf-8")


class VisualProductionError(RuntimeError):
    pass


class VisualProductionService:
    NEGATIVE_PROMPT = (
        "text, watermark, logo, extra fingers, distorted hands, inconsistent clothing, "
        "inconsistent face, duplicate people, anachronistic props, caricature"
    )

    def __init__(self, database: Database, provider: VisualProvider | None = None):
        self.db = database
        self.provider = provider or MockSVGProvider()

    def _project(self, project_id: str) -> tuple[dict, Storyboard]:
        rows = self.db.execute("SELECT * FROM projects WHERE id=?", (project_id,))
        if not rows:
            raise VisualProductionError(f"Unknown project: {project_id}")
        row = dict(rows[0])
        try:
            storyboard_path = self.db.resolve_project_file(
                row["storyboard_path"], expected_hash=row["storyboard_hash"])
        except FileNotFoundError as exc:
            raise VisualProductionError(str(exc)) from exc
        storyboard = load_storyboard(storyboard_path)
        return row, storyboard

    @staticmethod
    def _continuity_prompt(storyboard: Storyboard, shot_prompt: str) -> str:
        characters = "\n".join(
            f"{name}: {char.descriptor}" for name, char in storyboard.characters.items()
        )
        return (
            "Create one cinematic storyboard keyframe. Preserve exact character identity, "
            "age, face, hair, wardrobe and recurring props across all shots. "
            "Culturally respectful Ethiopian coffee ceremony; natural materials and "
            "believable hands; no written text.\nCHARACTER CONTINUITY BIBLE:\n"
            f"{characters}\nSHOT DIRECTION:\n{shot_prompt}"
        )

    def generate(self, project_id: str, output_dir: str | Path, *, width: int = 1024,
                 height: int = 576, seed_base: int = 41000) -> dict:
        if width < 256 or height < 256 or width > 2048 or height > 2048:
            raise ValueError("Preview dimensions must be between 256 and 2048 pixels")
        project, storyboard = self._project(project_id)
        output = Path(output_dir).resolve() / project_id
        output.mkdir(parents=True, exist_ok=True)
        orch = Orchestrator(self.db)
        run_id = orch.create_run(project_id, config={
            "stage": "phase3_visual_development", "provider": self.provider.name,
            "provider_version": self.provider.version, "width": width, "height": height,
            "seed_base": seed_base,
        })
        # Character references are generated first; all shot keyframes depend on them.
        ref_jobs: list[str] = []
        jobs: list[tuple[str, str, str, str, dict]] = []
        for index, (name, character) in enumerate(storyboard.characters.items()):
            prompt = ("Character reference sheet for a fictional film character. "
                      "Show a consistent full-body design, neutral pose, readable clothing "
                      "silhouette and restrained natural palette. " + character.descriptor)
            inputs = {"prompt": prompt, "negative": self.NEGATIVE_PROMPT,
                      "width": width, "height": height}
            jid, cached = orch.add_job(run_id, stage="character_reference", subject_id=name,
                inputs=inputs, model=self.provider.name, model_version=self.provider.version,
                config={"seed": seed_base + index})
            ref_jobs.append(jid)
            jobs.append((jid, "character_reference", name, prompt,
                         {"seed": seed_base + index, "cached": cached}))
        for index, shot in enumerate(storyboard.shots, start=1):
            prompt = self._continuity_prompt(storyboard, shot.image_prompt)
            inputs = {"prompt": prompt, "negative": self.NEGATIVE_PROMPT,
                      "width": width, "height": height}
            jid, cached = orch.add_job(run_id, stage="shot_keyframe", subject_id=shot.id,
                inputs=inputs, model=self.provider.name, model_version=self.provider.version,
                config={"seed": seed_base + 100 + index}, dependencies=ref_jobs)
            jobs.append((jid, "shot_keyframe", shot.id, prompt,
                         {"seed": seed_base + 100 + index, "cached": cached}))
        orch.start_run(run_id)
        generated, reused = [], []
        job_specs = {item[0]: item[1:] for item in jobs}
        reused.extend(item[2] for item in jobs if item[4]["cached"])
        pending = {item[0] for item in jobs if not item[4]["cached"]}
        while pending:
            job = orch.claim_ready_job(run_id, worker="local-visual-worker")
            if not job or job["id"] not in pending:
                raise VisualProductionError("No eligible visual job; dependency graph is blocked")
            job_id = job["id"]
            stage, subject, prompt, meta = job_specs[job_id]
            pending.remove(job_id)
            filename = f"{stage}_{subject}.svg"
            path = output / filename
            try:
                self.provider.generate(prompt=prompt, negative_prompt=self.NEGATIVE_PROMPT,
                    output_path=path, width=width, height=height, seed=meta["seed"])
                prompt_path = path.with_suffix(".prompt.json")
                prompt_path.write_text(json.dumps({"prompt": prompt,
                    "negative_prompt": self.NEGATIVE_PROMPT, "seed": meta["seed"],
                    "provider": self.provider.name, "provider_version": self.provider.version},
                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                orch.complete_job(job_id, artifact_path=path, media_type="image/svg+xml",
                    metadata={"preview_only": isinstance(self.provider, MockSVGProvider),
                              "prompt_path": str(prompt_path), "provider": self.provider.name,
                              "provider_version": self.provider.version, "seed": meta["seed"]})
                generated.append(str(path))
            except Exception as exc:
                orch.fail_job(job_id, str(exc), retry=False)
                orch.finish_run_if_complete(run_id)
                raise VisualProductionError(f"Failed {stage}:{subject}: {exc}") from exc
        status = orch.finish_run_if_complete(run_id)
        artifacts = self.db.execute("SELECT stage,subject_id,path,content_hash,media_type,metadata_json "
                                    "FROM artifacts WHERE project_id=? AND run_id=? ORDER BY stage,subject_id",
                                    (project_id, run_id))
        manifest = {"project_id": project_id, "run_id": run_id, "run_status": status,
            "provider": self.provider.name, "provider_version": self.provider.version,
            "preview_only": isinstance(self.provider, MockSVGProvider),
            "storyboard_hash": project["storyboard_hash"],
            "artifacts": [dict(a) for a in artifacts],
            "generated_this_run": generated, "cache_reused_subjects": reused}
        manifest_path = output / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest
