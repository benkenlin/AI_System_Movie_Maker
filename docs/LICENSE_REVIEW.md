# Model and Output License Review Procedure

The release gate intentionally starts blocked. A model name or an upstream repository's code license is not enough to prove that a particular checkpoint and generated output are cleared for a particular use.

## Review each model entry

For each `image`, `video`, `music` and `tts` entry in `model_licenses.json`:

1. Record the exact provider, model ID, checkpoint/revision and version used in the run.
2. Open the linked official model/provider terms and the license file distributed with the exact weights.
3. Check commercial use, attribution, redistribution, output rights, usage restrictions, data handling and any separate partner terms.
4. Record the exact license/terms summary, source URL, reviewer and review date.
5. Set `reviewed: true` only after reviewing the exact model/checkpoint terms.
6. Set `commercial_use_reviewed: true` only if the intended use is explicitly allowed or the applicable conditions are satisfied. If uncertain, leave false and obtain clarification.

## Current project references

| Component | Configured model | Starting reference | Important qualification |
|---|---|---|---|
| Image | Cloudflare `@cf/black-forest-labs/flux-2-klein-9b` | https://developers.cloudflare.com/workers-ai/models/flux-2-klein-9b/ | Cloudflare lists this as a partner-hosted model; follow the linked model-specific terms. |
| Video | Wan 2.2 TI2V-5B | https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers | The model card identifies Apache-2.0; verify the exact downloaded checkpoint and revision. |
| Music | ACE-Step 1.5 | https://github.com/ace-step/ACE-Step-1.5 | Review code and model-weight licenses separately; verify the exact DiT/LM checkpoints. |
| TTS | Gemini 3.8 Flash TTS | https://ai.google.dev/gemini-api/terms | Review the current Gemini API terms, data-use and output conditions for your account. |

## Complete the registry

The included `model_licenses.json` starter has all review flags set to false. Do not simply change every flag to true. The release gate checks:

- `release_reviewed` — the full registry has been reviewed;
- `output_rights_reviewed` — generated-output rights have been reviewed;
- each model has `model`, `license`, `source_url`, `reviewed: true` and `commercial_use_reviewed: true`;
- reviewer and review date are recorded.

If a model's terms do not grant the intended use, replace the model or restrict the output use. Keep the registry truthful and keep private consent evidence out of Git.
