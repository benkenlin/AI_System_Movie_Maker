# scripts/assemble_fast.sh
# Usage: bash scripts/assemble_fast.sh outputs/keyframes/s01.png outputs/audio/s01.wav outputs/music/score.wav
set -euo pipefail

IMG_IN="${1:?Provide keyframe image path}"
VOX_IN="${2:?Provide narration WAV path}"
MUS_IN="${3:?Provide music WAV path}"
OUT_DIR="outputs/fast_cut"
mkdir -p "$OUT_DIR"

# 1. Ken Burns on keyframe (6s @ 24fps = 144 frames, gentle push-in, subject centered)
ffmpeg -y -hide_banner -loglevel error \
  -i "$IMG_IN" \
  -vf "scale=3840:-2,zoompan=z='min(zoom+0.0007,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=144:s=1280x704:fps=24,format=yuv420p" \
  -c:v libx264 -crf 16 -preset fast "$OUT_DIR/clip_16x9.mp4"

# 2. Vertical 9:16 crop + scale (centered)
ffmpeg -y -hide_banner -loglevel error \
  -i "$OUT_DIR/clip_16x9.mp4" \
  -vf "crop=w='trunc(ih*9/16/2)*2':h=ih:x='(iw-ow)*0.5':y=0,scale=1080:1920:flags=lanczos,format=yuv420p" \
  -c:v libx264 -crf 16 -preset fast "$OUT_DIR/clip_9x16.mp4"

# 3. Prep narration (48kHz mono) & music bed (48kHz stereo, 6s), then sidechain duck music under voice
ffmpeg -y -hide_banner -loglevel error -i "$VOX_IN" -af "aresample=48000,aformat=channel_layouts=mono" "$OUT_DIR/vox_48k.wav"
ffmpeg -y -hide_banner -loglevel error -stream_loop -1 -i "$MUS_IN" -t 6 -af "aresample=48000,aformat=channel_layout=stereo,volume=-10dB" "$OUT_DIR/mus_48k.wav"

ffmpeg -y -hide_banner -loglevel error \
  -i "$OUT_DIR/mus_48k.wav" -i "$OUT_DIR/vox_48k.wav" \
  -filter_complex "[1:a]aformat=channel_layout=stereo,asplit=2[v][sc];[0:a][sc]sidechaincompress=threshold=0.04:ratio=8:attack=15:release=450:makeup=1[ducked];[ducked][v]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]" \
  -map "[mix]" -ar 48000 "$OUT_DIR/mix_pre.wav"

# 4. Loudness normalization (-16 LUFS, -1.5 dBTP)
ffmpeg -y -hide_banner -loglevel error -i "$OUT_DIR/mix_pre.wav" \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true" -ar 48000 "$OUT_DIR/mix_final.wav"

# 5. Mux both aspect ratios with AI disclosure metadata
ffmpeg -y -hide_banner -loglevel error \
  -i "$OUT_DIR/clip_16x9.mp4" -i "$OUT_DIR/mix_final.wav" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -movflags +faststart -shortest \
  -metadata comment="Created with AI tools" "$OUT_DIR/out_16x9.mp4"

ffmpeg -y -hide_banner -loglevel error \
  -i "$OUT_DIR/clip_9x16.mp4" -i "$OUT_DIR/mix_final.wav" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -movflags +faststart -shortest \
  -metadata comment="Created with AI tools" "$OUT_DIR/out_9x16.mp4"

echo "Wrote $OUT_DIR/out_16x9.mp4 and $OUT_DIR/out_9x16.mp4"
```[cite: 56, 57, 58, 59, 60, 70]