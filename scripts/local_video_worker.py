from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def parse_args(argv: list[str]) -> tuple[Path | None, Path | None]:
    in_path: Path | None = None
    out_path: Path | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--input", "-i") and i + 1 < len(argv):
            in_path = Path(argv[i + 1])
            i += 2
        elif arg in ("--output", "-o") and i + 1 < len(argv):
            out_path = Path(argv[i + 1])
            i += 2
        else:
            i += 1
    if out_path is None and argv:
        out_path = Path(argv[-1])
    return in_path, out_path


def build_motion_filter(shot_id: str, duration_s: float, seed_val: int) -> str:
    # Distinct smooth camera trajectories per shot index so consecutive shots vary naturally
    modes = [
        "zoom_in_right",
        "pan_left_drift",
        "zoom_in_center",
        "pan_right_drift",
        "gentle_push_up",
        "slow_pull_back",
        "pan_left_zoom",
        "gentle_drift_out",
    ]
    mode = modes[seed_val % len(modes)]
    fps = 24
    total_frames = max(24, int(round(duration_s * fps)))
    p = f"min(on/{total_frames},1.0)"
    ease = f"({p}*{p}*(3-2*{p}))"

    # Work at 1920x1080 then interpolate smoothly and output clean 1280x720 H.264
    if mode == "zoom_in_right":
        z_expr = f"1.0+0.10*{ease}"
        x_expr = f"(iw-iw/zoom)*(0.45+0.20*{ease})"
        y_expr = f"(ih-ih/zoom)*0.5"
    elif mode == "pan_left_drift":
        z_expr = f"1.06+0.03*{ease}"
        x_expr = f"(iw-iw/zoom)*(0.75-0.45*{ease})"
        y_expr = f"(ih-ih/zoom)*(0.48+0.04*{ease})"
    elif mode == "zoom_in_center":
        z_expr = f"1.0+0.11*{ease}"
        x_expr = f"(iw-iw/zoom)*0.5"
        y_expr = f"(ih-ih/zoom)*(0.52-0.06*{ease})"
    elif mode == "pan_right_drift":
        z_expr = f"1.06+0.03*{ease}"
        x_expr = f"(iw-iw/zoom)*(0.25+0.45*{ease})"
        y_expr = f"(ih-ih/zoom)*(0.52-0.04*{ease})"
    elif mode == "gentle_push_up":
        z_expr = f"1.02+0.08*{ease}"
        x_expr = f"(iw-iw/zoom)*(0.5+0.05*sin(3.14159*{p}))"
        y_expr = f"(ih-ih/zoom)*(0.62-0.22*{ease})"
    elif mode == "slow_pull_back":
        z_expr = f"1.11-0.09*{ease}"
        x_expr = f"(iw-iw/zoom)*0.5"
        y_expr = f"(ih-ih/zoom)*0.5"
    elif mode == "pan_left_zoom":
        z_expr = f"1.03+0.08*{ease}"
        x_expr = f"(iw-iw/zoom)*(0.70-0.35*{ease})"
        y_expr = f"(ih-ih/zoom)*0.5"
    else:
        z_expr = f"1.08-0.05*{ease}"
        x_expr = f"(iw-iw/zoom)*(0.35+0.30*{ease})"
        y_expr = f"(ih-ih/zoom)*0.5"

    # Use high-res source scaling before zoompan to avoid sub-pixel shimmer,
    # then smooth motion with minterpolate and downscale to 1280x720.
    return (
        f"scale=2560:1440:force_original_aspect_ratio=increase,crop=2560:1440,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s=1920x1080:fps={fps},"
        f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
        f"scale=1280:720:flags=lanczos,setsar=1,format=yuv420p"
    )


def main() -> None:
    in_path, out_path = parse_args(sys.argv[1:])
    if out_path is None:
        raise SystemExit("Missing --output path")

    payload = {}
    if in_path and in_path.exists():
        payload = json.loads(in_path.read_text(encoding="utf-8"))

    image_path = Path(payload.get("image", ""))
    if not image_path.exists():
        raise SystemExit(f"Input image does not exist: {image_path}")

    shot_id = str(payload.get("shot_id", "s01"))
    duration_s = float(payload.get("duration_s", 7.0))
    seed_raw = payload.get("seed")
    if isinstance(seed_raw, int):
        seed_val = seed_raw
    else:
        digest = hashlib.sha256(f"{shot_id}:{payload.get('keyframe_sha256', '')}".encode("utf-8")).hexdigest()
        seed_val = int(digest[:8], 16)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = build_motion_filter(shot_id, duration_s, seed_val)

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-vf",
        vf,
        "-t",
        f"{duration_s:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
