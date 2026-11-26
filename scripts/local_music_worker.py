from __future__ import annotations

import json
import math
import struct
import sys
import wave
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


def main() -> None:
    in_path, out_path = parse_args(sys.argv[1:])
    if out_path is None:
        out_path = Path("outputs/music/candidate_0.wav")

    duration_s = 65.00
    seed = 1000
    if in_path and in_path.exists():
        try:
            payload = json.loads(in_path.read_text(encoding="utf-8"))
            for k in ("duration_s", "target_runtime_s"):
                if isinstance(payload.get(k), (int, float)) and payload[k] > 0:
                    duration_s = max(float(payload[k]) + 2.0, duration_s)
                    break
            if isinstance(payload.get("seed"), int):
                seed = int(payload["seed"])
        except Exception:
            pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sr = 24000
    n_samples = int(sr * duration_s)

    # Adventurous ascending Dorian / epic-journey progression (in Hz)
    # Root D3 (146.83), E3 (164.81), F3 (174.61), G3 (196.00), A3 (220.00), B3 (246.94), C4 (261.63), D4 (293.66), E4 (329.63), A4 (440.00)
    phrases = [
        [146.83, 220.00, 261.63, 293.66, 329.63, 293.66, 261.63, 220.00],  # quest motif A
        [174.61, 220.00, 261.63, 329.63, 440.00, 329.63, 293.66, 261.63],  # rising discovery
        [196.00, 246.94, 293.66, 329.63, 440.00, 493.88, 440.00, 329.63],  # forward momentum
        [146.83, 220.00, 293.66, 329.63, 440.00, 329.63, 293.66, 220.00],  # heroic resolution
    ]
    phrase_choice = phrases[seed % len(phrases)]
    bass_roots = [146.83, 174.61, 196.00, 220.00]

    step_dur = 0.50   # 120 BPM eighth-note drive
    beat_dur = 1.00   # quarter-note adventure pulse

    fade_in_s = 1.5
    fade_out_s = 3.0
    master_gain = 0.28

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)

        for start in range(0, n_samples, sr):
            end = min(n_samples, start + sr)
            buf = bytearray()
            for n in range(start, end):
                t = n / sr

                # Overall adventure arc: build through middle, resolve cleanly at end
                progress = min(1.0, max(0.0, t / max(1.0, duration_s)))
                arc = 0.75 + 0.35 * math.sin(math.pi * min(1.0, progress * 1.15))
                env_in = min(1.0, t / fade_in_s)
                env_out = min(1.0, max(0.0, (duration_s - t) / fade_out_s))
                env = env_in * env_out * arc

                # 1. Adventure bass & fifth pedal
                bar_idx = int(t / 4.0) % len(bass_roots)
                b_root = bass_roots[bar_idx]
                b_fifth = b_root * 1.498
                bass = 0.32 * math.sin(2.0 * math.pi * b_root * t) + 0.16 * math.sin(2.0 * math.pi * b_fifth * t)

                # 2. Warm rhythmic adventure pulse (soft low tom/drum hit every quarter beat + accent every 4th beat)
                beat_pos = t % beat_dur
                bar_beat = int(t / beat_dur) % 4
                drum_amp = 0.34 if bar_beat in (0, 2) else 0.20
                if bar_beat == 3:
                    drum_amp = 0.28
                pitch_drop = 92.0 * math.exp(-14.0 * beat_pos) + 46.0
                drum_env = math.exp(-9.5 * beat_pos) * (1.0 - math.exp(-80.0 * beat_pos))
                pulse = drum_amp * drum_env * math.sin(2.0 * math.pi * pitch_drop * beat_pos)

                # 3. Sweeping lead melody (eighth-note steps with bright harmonics)
                step_idx = int(t / step_dur) % len(phrase_choice)
                step_t = t % step_dur
                note_freq = phrase_choice[step_idx]
                # Slight octave lift during second half of the film
                if progress > 0.45 and step_idx in (3, 4, 5):
                    note_freq *= 1.5 if progress > 0.65 else 1.0
                lead_env = math.exp(-3.2 * step_t) * (1.0 - math.exp(-50.0 * step_t))
                lead = 0.42 * lead_env * (
                    0.65 * math.sin(2.0 * math.pi * note_freq * t)
                    + 0.25 * math.sin(2.0 * math.pi * (note_freq * 2.0) * t)
                    + 0.10 * math.sin(2.0 * math.pi * (note_freq * 3.0) * t)
                )

                # 4. Shimmering harmonic pad fifth/octave underneath
                pad = 0.14 * (
                    math.sin(2.0 * math.pi * (b_root * 2.0) * t + 0.15 * math.sin(2.0 * math.pi * 0.4 * t))
                    + 0.6 * math.sin(2.0 * math.pi * (b_fifth * 2.0) * t)
                )

                val = master_gain * env * (bass + pulse + lead + pad)
                sample = max(-32767, min(32767, int(val * 32767)))
                buf.extend(struct.pack("<h", sample))
            wf.writeframes(bytes(buf))


if __name__ == "__main__":
    main()
