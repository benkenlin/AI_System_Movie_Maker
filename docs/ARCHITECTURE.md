# Architecture at a glance

```text
Idea -> Gemini planner -> storyboard.json -> schema/semantic validation
     -> deterministic orchestrator + content-hash cache
        -> Cloudflare FLUX keyframes -> keyframe approval
        -> Wan 2.2 video worker (Ken Burns fallback)
        -> ACE-Step 1.5 music candidates -> automatic score selection
        -> Gemini TTS narration -> Gemini audio/translation screening
     -> FFmpeg assembly -> 16:9 + 9:16 exports -> release gates + QC
```

The orchestrator owns ordering, retries, caching, logs and resource limits. Model adapters perform bounded inference tasks. The storyboard is the single stage contract. Music is automatically selected using technical metrics and the decision rationale is saved; native-speaker narration approval, consent and model-license review remain explicit release gates.
