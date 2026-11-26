# scripts/generate_keyframes_cf.py
import base64
import json
import os
import time
from pathlib import Path
import requests
from PIL import Image

ROOT = Path(".")
SB_PATH = ROOT / "storyboard.json"
REFS_DIR = ROOT / "outputs/refs"
CROPS_DIR = ROOT / "outputs/crops"
KF_DIR = ROOT / "outputs/keyframes"
LOG_PATH = ROOT / "runs.jsonl"

CF_ACCOUNT = os.environ["CF_ACCOUNT_ID"]
CF_TOKEN = os.environ["CF_API_TOKEN"]
MODEL_ID = "@cf/black-forest-labs/flux-2-klein-9b"
ENDPOINT = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/run/{MODEL_ID}"


def log_run(record: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def make_crop_under_512(src_path: Path, dst_path: Path, box_frac=(0.25, 0.05, 0.75, 0.55)):
    img = Image.open(src_path).convert("RGB")
    w, h = img.size
    crop = img.crop((int(w * box_frac[0]), int(h * box_frac[1]), int(w * box_frac[2]), int(h * box_frac[3])))
    crop.thumbnail((480, 480), Image.Resampling.LANCZOS)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(dst_path, format="PNG")
    return dst_path


def call_flux_klein(prompt: str, ref_paths: list[Path], out_path: Path, seed: int = 42, width: int = 1280, height: int = 704):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    files = {
        "prompt": (None, prompt),
        "width": (None, str(width)),
        "height": (None, str(height)),
        "seed": (None, str(seed)),
    }
    handles = []
    try:
        for idx, rp in enumerate(ref_paths[:4]):
            fh = rp.open("rb")
            handles.append(fh)
            files[f"input_image_{idx}"] = (rp.name, fh, "image/png")

        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {CF_TOKEN}"},
            files=files,
            timeout=180,
        )
        latency = round(time.time() - t0, 3)
        if not resp.ok:
            log_run({
                "stage": "keyframes",
                "model": MODEL_ID,
                "seed": seed,
                "width": width,
                "height": height,
                "latency_s": latency,
                "ok": False,
                "error": resp.text[:300],
            })
            raise RuntimeError(f"Cloudflare error {resp.status_code}: {resp.text[:300]}")

        b64 = resp.json()["result"]["image"]
        out_path.write_bytes(base64.b64decode(b64))
        log_run({
            "stage": "keyframes",
            "model": MODEL_ID,
            "seed": seed,
            "width": width,
            "height": height,
            "latency_s": latency,
            "ok": True,
            "output": str(out_path),
        })
    finally:
        for fh in handles:
            fh.close()


def main():
    sb = json.loads(SB_PATH.read_text(encoding="utf-8"))
    style_block = sb["style"]["block"]
    chars = sb["characters"]

    # 1. Build <512px crops from existing character reference sheets if present
    active_crops = []
    for cid, cdata in chars.items():
        ref_sheet = Path(cdata.get("ref_sheet", REFS_DIR / f"{cid}.png"))
        if ref_sheet.exists():
            face_crop = make_crop_under_512(ref_sheet, CROPS_DIR / f"{cid}_face.png", (0.25, 0.05, 0.75, 0.50))
            body_crop = make_crop_under_512(ref_sheet, CROPS_DIR / f"{cid}_body.png", (0.15, 0.05, 0.85, 0.95))
            active_crops.extend([face_crop, body_crop])

    # 2. Generate keyframes for shots that don't have one yet
    for s in sb["shots"]:
        out_kf = KF_DIR / f"{s['id']}.png"
        if out_kf.exists():
            continue
        char_notes = []
        for idx, rp in enumerate(active_crops[:4]):
            char_notes.append(f"Use reference image {idx} for consistent character appearance.")
        full_prompt = (
            f"{style_block}. "
            f"{' '.join(char_notes)} "
            f"Scene: {s['image_prompt']}. "
            "Subject centered in frame with safe margin on left and right for 9:16 crop. No text or watermarks."
        )
        seed = int(s.get("seed", 100))
        call_flux_klein(full_prompt, active_crops, out_kf, seed=seed, width=1280, height=704)
        time.sleep(1.0)


if __name__ == "__main__":
    main()


    #```[cite: 40, 62, 63, 64, 65, 67, 72]