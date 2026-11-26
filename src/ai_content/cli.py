from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .db import Database
from .orchestrator import Orchestrator, OrchestratorError
from .planning import DraftService, PlanningError
from .validation import StoryboardValidationError, export_json_schema, load_storyboard
from .visual import VisualProductionService, VisualProductionError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-content")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate storyboard JSON")
    validate.add_argument("storyboard")
    export = sub.add_parser("export-schema", help="export the JSON Schema")
    export.add_argument("destination")
    init = sub.add_parser("init-project", help="validate and register a storyboard in SQLite")
    init.add_argument("storyboard")
    init.add_argument("--db", default="outputs/system.db")
    status = sub.add_parser("status", help="show a run and its jobs")
    status.add_argument("run_id")
    status.add_argument("--db", default="outputs/system.db")
    events = sub.add_parser("export-events", help="export run audit events as JSONL")
    events.add_argument("run_id")
    events.add_argument("destination")
    events.add_argument("--db", default="outputs/system.db")
    plan = sub.add_parser("plan", help="create a storyboard draft for human review")
    plan.add_argument("idea", help="short film concept")
    plan.add_argument("--title", default="The Last Coffee Ceremony")
    plan.add_argument("--language", default="am")
    plan.add_argument("--subtitle-language", default="en")
    plan.add_argument("--max-repairs", type=int, default=2)
    plan.add_argument("--offline", action="store_true", help="use the deterministic offline template instead of Gemini")
    plan.add_argument("--db", default="outputs/system.db")
    show = sub.add_parser("show-draft", help="show a storyboard draft and approval status")
    show.add_argument("draft_id")
    show.add_argument("--db", default="outputs/system.db")
    approve = sub.add_parser("approve-draft", help="approve a draft and register its project")
    approve.add_argument("draft_id")
    approve.add_argument("destination", help="where to write the approved storyboard JSON")
    approve.add_argument("--db", default="outputs/system.db")
    reject = sub.add_parser("reject-draft", help="reject a draft with a reason")
    reject.add_argument("draft_id")
    reject.add_argument("reason")
    reject.add_argument("--db", default="outputs/system.db")
    film = sub.add_parser("film", help="run the complete film pipeline with explicit human review checkpoints")
    film.add_argument('storyboard', nargs='?', default='storyboard.json')
    film.add_argument('--output', default='outputs')
    film.add_argument('--licenses', default='model_licenses.json')
    film.add_argument('--consent', default='consent_registry.json')
    visual = sub.add_parser("visualize", help="generate character references and shot keyframe previews")
    visual.add_argument("project_id")
    visual.add_argument("--output", default="outputs/visuals")
    visual.add_argument("--width", type=int, default=1024)
    visual.add_argument("--height", type=int, default=576)
    visual.add_argument("--seed", type=int, default=41000)
    visual.add_argument("--db", default="outputs/system.db")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate":
            storyboard = load_storyboard(args.storyboard)
            seconds = sum(s.duration_s for s in storyboard.shots)
            print(f"VALID: {storyboard.title!r} — {len(storyboard.shots)} shots, {seconds} seconds")
            return 0
        if args.command == "export-schema":
            print(f"JSON Schema written to {export_json_schema(args.destination)}")
            return 0
        if args.command == "init-project":
            orch = Orchestrator(Database(args.db))
            project_id = orch.register_project(args.storyboard)
            run_id = orch.create_run(project_id, config={"film_language": "am", "subtitle_language": "en"})
            print(json.dumps({"project_id": project_id, "run_id": run_id}, indent=2))
            return 0
        if args.command == "status":
            print(json.dumps(Orchestrator(Database(args.db)).status(args.run_id), indent=2))
            return 0
        if args.command == "export-events":
            path = Orchestrator(Database(args.db)).export_events_jsonl(args.run_id, args.destination)
            print(f"Events exported to {path}")
            return 0
        if args.command == "plan":
            from .planning import MockPlanner
            from .providers import ProviderConfig, GeminiTextPlanner
            planner = MockPlanner() if args.offline else GeminiTextPlanner(ProviderConfig.from_env())
            draft = DraftService(Database(args.db), planner=planner, max_repairs=args.max_repairs).create_draft(
                args.idea, title=args.title, language=args.language,
                subtitle_language=args.subtitle_language)
            print(json.dumps({"draft_id": draft["id"], "status": draft["status"],
                              "title": draft["title"], "repair_attempts": draft["repair_attempts"],
                              "issues": draft["issues"]}, ensure_ascii=False, indent=2))
            return 0 if draft["status"] == "pending_approval" else 1
        if args.command == "show-draft":
            print(json.dumps(DraftService(Database(args.db)).get_draft(args.draft_id),
                             ensure_ascii=False, indent=2))
            return 0
        if args.command == "approve-draft":
            project_id, path = DraftService(Database(args.db)).approve(args.draft_id, args.destination)
            print(json.dumps({"project_id": project_id, "storyboard": str(path),
                              "production_jobs_scheduled": False}, indent=2))
            return 0
        if args.command == "reject-draft":
            DraftService(Database(args.db)).reject(args.draft_id, args.reason)
            print("Draft rejected.")
            return 0
        if args.command == "film":
            from .providers import ProviderRegistry
            from .production import ProductionPipeline
            from .music import auto_select_music_candidate
            from .review import audit_narration_assets, approve_native_review
            from .assembly import FilmAssembler, final_quality_check
            from .ethics import check_release_gates
            import json as _json
            sb_path = Path(args.storyboard).resolve(); output = Path(args.output).resolve()
            sb = load_storyboard(sb_path); registry = ProviderRegistry(); pipeline = ProductionPipeline(output, registry, Path('runs.jsonl'))
            refs = pipeline.generate_character_references(sb); frames = pipeline.generate_keyframes(sb)
            print(f'Generated/reused {len(refs)} character references and {len(frames)} keyframes.')
            print(f'Review the keyframes in: {output / "keyframes"}')
            if input('Type APPROVE after inspecting every keyframe: ').strip() != 'APPROVE':
                print('Stopped before GPU video generation; no keyframe approval recorded.', file=sys.stderr); return 2
            keyframe_reviewer = input('Keyframe reviewer name: ').strip()
            if not keyframe_reviewer: print('A keyframe reviewer name is required.', file=sys.stderr); return 2
            pipeline.approve_keyframes(sb, keyframe_reviewer)
            clips = pipeline.generate_clips(sb); print(f'Generated/reused {len(clips)} moving shots or fallbacks.')
            narration = pipeline.generate_narration(sb); print(f'Generated/reused {len(narration)} narration files.')
            candidates = pipeline.generate_music(sb)
            selection = auto_select_music_candidate(sb_path, candidates, log_path=Path('runs.jsonl'))
            print('Automatic music selection:', selection['selected']); print(selection['rationale'])
            sb = load_storyboard(sb_path)
            audit = audit_narration_assets(sb, output/'narration', output/'narration_review.json')
            print('Narration technical audit:', 'passed' if audit['automated_checks_passed'] else 'failed')
            if not audit['automated_checks_passed']:
                print(audit['notes'], file=sys.stderr); return 2
            reviewer = input('Native-speaker reviewer name (after listening to every narration file): ').strip()
            if input('Type APPROVE only if pronunciation, meaning and English subtitles are correct: ').strip() != 'APPROVE':
                print('Stopped: native-speaker review not approved.', file=sys.stderr); return 2
            approve_native_review(output/'narration_review.json', reviewer, True)
            check_release_gates(sb, args.consent, licenses_path=args.licenses, narration_review_path=output/'narration_review.json')
            paths = FilmAssembler(output).assemble(sb, music=Path(sb.music.selected), registry_path=args.consent, licenses_path=args.licenses, narration_review_path=output/'narration_review.json')
            qc = final_quality_check(paths); (output/'final_qc.json').write_text(_json.dumps(qc,indent=2),encoding='utf-8')
            print(_json.dumps({k:str(v) for k,v in paths.items()},indent=2)); print('Final QC passed.')
            return 0
        if args.command == "visualize":
            result = VisualProductionService(Database(args.db)).generate(
                args.project_id, args.output, width=args.width, height=args.height, seed_base=args.seed)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["run_status"] == "succeeded" else 1
    except (StoryboardValidationError, OrchestratorError, PlanningError, VisualProductionError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
