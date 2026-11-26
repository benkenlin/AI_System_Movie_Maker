# Phase 3 — Character references and storyboard keyframes

## Scope

Phase 3 adds a provider-neutral visual-production boundary. It reads only a validated,
registered storyboard, creates character-reference assets first, then shot keyframes whose
prompts include a shared character-continuity bible. Every generated asset receives a SHA-256
content hash and a SQLite artifact record. Prompt/seed/provider sidecars are retained for
reproducibility and review.

## Run

Register an approved storyboard if it is not already registered:

```bash
ai-content init-project outputs/approved/the_last_coffee_ceremony.json --db outputs/system.db
```

Copy the returned `project_id`, then run visual development:

```bash
ai-content visualize PROJECT_ID --output outputs/visuals --width 1024 --height 576 --db outputs/system.db
```

For a quick local smoke test, use `--width 512 --height 288`. Output is stored under
`outputs/visuals/PROJECT_ID/`, including character reference SVGs, shot keyframe SVGs,
`.prompt.json` sidecars and `manifest.json`.

## Provider boundary and current limitation

`VisualProvider` is the adapter contract. An image-model adapter can implement `generate()`
without changing planning, hashing, persistence, or orchestration. The default
`MockSVGProvider` is intentionally offline and deterministic: it creates labelled SVG visual
layout cards to test the pipeline. These are **not AI-generated illustrations, finished
character designs, or production keyframes**. Do not submit them as final creative assets.

The adapter receives a positive prompt, negative prompt, dimensions and deterministic seed.
The shot prompt includes all storyboard character descriptors to encourage identity and
wardrobe continuity. This is prompt-level conditioning, not a guarantee of visual identity.
A production image adapter should additionally support reference-image conditioning, record
model/checkpoint and scheduler versions, expose safety/licensing metadata, and persist the
actual returned image bytes. Human review remains required before downstream video generation.

## Artifact identity and caching

The cache key includes stage, subject, positive/negative prompt, dimensions, provider name and
version, and seed. Identical requests reuse the existing artifact rather than invoking the
provider again. Changing prompt, provider version, dimensions or seed invalidates the cache.
The manifest includes project/storyboard identity, run, provider, asset paths and content hashes.

## Tests and limits

Tests cover dependency-gated execution, reference and keyframe counts, prompt sidecars, content
hashes, cache reuse, and provider replacement. The default provider is a pipeline test double;
no Kaggle/Colab GPU is invoked and no real image model is benchmarked in this phase. The visual
provider currently executes locally in-process; remote worker dispatch, image-reference
conditioning, image quality scoring, contact-sheet review UI and human asset approval are next.
