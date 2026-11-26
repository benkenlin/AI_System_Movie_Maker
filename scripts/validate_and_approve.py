# scripts/validate_and_approve.py
import hashlib
import json
import sys
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(".")
SB_PATH = ROOT / "storyboard.json"
SCHEMA_PATH = ROOT / "schema/storyboard.schema.json"
KEYFRAME_DIR = ROOT / "outputs/keyframes"
APPROVAL_PATH = ROOT / "outputs/approved_keyframes.json"

ALLOWED_CAMS = {"static", "push_in", "pan_right"}
WPS = {"en": 2.2, "am": 1.8, "om": 1.9, "default": 2.0}


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    sb = json.loads(SB_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    schema_errs = [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(sb)
    ]
    if schema_errs:
        for err in schema_errs:
            print("SCHEMA ERROR:", err)
        sys.exit(1)

    errs = []
    chars = sb.get("characters", {})
    if not (1 <= len(chars) <= 2):
        errs.append(f"expected 1-2 characters, found {len(chars)}")

    for cid, c in chars.items():
        if c.get("origin") != "fictional":
            errs.append(f"character '{cid}' origin must be 'fictional' for fast-track")

    shots = sb["shots"]
    if sb.get("shot_count") != len(shots):
        errs.append("shot_count does not match len(shots)")

    total_words = 0
    for idx, s in enumerate(shots, start=1):
        sid = s["id"]
        if sid != f"s{idx:02d}":
            errs.append(f"shot id '{sid}' expected 's{idx:02d}'")
        if s.get("camera") not in ALLOWED_CAMS:
            errs.append(f"{sid}: camera '{s.get('camera')}' not in {sorted(ALLOWED_CAMS)}")
        if len(s.get("characters", [])) > 2:
            errs.append(f"{sid}: too many characters in shot (>2)")
        for c in s.get("characters", []):
            if c not in chars:
                errs.append(f"{sid}: unknown character '{c}'")

        text = s.get("narration", {}).get("text", "").strip()
        lang = s.get("narration", {}).get("lang", sb.get("language", "en"))
        words = len(text.split())
        total_words += words
        max_words = max(1, int(s["duration_s"] * WPS.get(lang, WPS["default"])))
        if words > max_words:
            errs.append(f"{sid}: narration ({words} words) exceeds ~{max_words} words for {s['duration_s']}s")

    if not (120 <= total_words <= 210):
        print(f"WARN: total narration words = {total_words} (target ~130-180 words)")

    if errs:
        for err in errs:
            print("SEMANTIC ERROR:", err)
        sys.exit(1)

    approvals = {}
    for s in shots:
        kf = KEYFRAME_DIR / f"{s['id']}.png"
        if kf.exists():
            approvals[s["id"]] = {
                "path": str(kf),
                "sha256": sha256_file(kf),
                "seed": s.get("seed"),
            }

    APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPROVAL_PATH.write_text(json.dumps(approvals, indent=2), encoding="utf-8")
    print(f"Validation passed ({len(shots)} shots). Approved keyframes recorded: {len(approvals)}")


if __name__ == "__main__":
    main()
# ```[cite: 27, 40, 47, 48, 50, 64, 72]

#```python