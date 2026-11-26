# Ethics, consent, and licensing

- Default all characters to fictional. Do not generate a real person's likeness or clone a real voice without documented, scoped permission.
- For each real person, create a private consent record, reference its ID in the storyboard, and add a registry entry with scope, date, expiry, evidence location, and `release_allowed: true` only after review.
- Use stock/prebuilt TTS voices; do not voice-clone. Keep narration text, pronunciation substitutions, and English subtitles separate.
- Review the exact model/checkpoint license, provider terms, training/output rights, attribution, and commercial-use restrictions. Record exact versions and review dates in `model_licenses.json`.
- Keep consent evidence and API credentials out of public Git. Publish only necessary consent metadata, never sensitive documents.
- Label AI-generated content visibly in the film end card and in public descriptions.
- Human review is required for cultural accuracy, keyframe quality, narration pronunciation and release. Music is selected automatically using technical metrics, but its cultural/aesthetic fit should still be auditioned before publication.
- The release gate blocks if any real-person consent is absent/unapproved or if model licenses are not marked reviewed.
