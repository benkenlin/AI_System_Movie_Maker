# Phase 2 — Story planning and human approval

## Scope

Phase 2 adds an offline, provider-neutral storyboard planning workflow on top of the Phase 1
validator and SQLite database. It does not generate images, audio, music or video and does not
schedule production jobs.

## Workflow

1. `Planner.plan()` converts the film idea into a storyboard-shaped Python dictionary.
2. `StoryCritic` validates it against the existing Pydantic `Storyboard` contract and checks
   project requirements: Amharic narration (`am`), English subtitles (`en`), and subtitle text
   for every shot.
3. If critique fails, `Planner.repair()` is called up to the configured bounded repair limit
   (0–5; default 2). A draft that still fails is stored as `needs_revision` and cannot be
   approved.
4. A valid draft is persisted in `storyboard_drafts` as `pending_approval` with its SHA-256
   payload hash, planner identifier, repair count and critique output.
5. A human reviews the draft, then explicitly approves or rejects it. Approval revalidates the
   payload, writes the approved JSON, and registers a project through the original validator.
   It deliberately creates no run and schedules no jobs.

## Commands

Create a draft (no external model/API calls):

```bash
ai-content plan "A family gathers for an Ethiopian coffee ceremony" \
  --title "The Last Coffee Ceremony" --language am --subtitle-language en \
  --db outputs/system.db
```

Inspect it:

```bash
ai-content show-draft DRAFT_ID --db outputs/system.db
```

After a human has reviewed the full storyboard JSON, approve it:

```bash
ai-content approve-draft DRAFT_ID outputs/approved/the_last_coffee_ceremony.json \
  --db outputs/system.db
```

Or reject it with a reason:

```bash
ai-content reject-draft DRAFT_ID "Revise the cultural details and pacing" \
  --db outputs/system.db
```

The approval command returns a project ID and explicitly reports that production jobs were not
scheduled. Phase 1 run/job creation remains a separate action after approval.

## Adapter contract

Implement the `Planner` protocol in `planning.py` to connect a chosen LLM provider. Keep provider
SDK calls outside the critic and draft persistence layers. The adapter must return JSON-compatible
data and should treat the film idea as untrusted content, not as instructions to bypass the
storyboard contract. Production adapters should request structured output, record model name and
version, apply time/token limits, and never auto-approve.

The included `MockPlanner` is a deterministic offline template, not an LLM. Its Amharic narration
and English subtitle lines are draft text and require review by a fluent Amharic speaker and a
cultural reviewer before release. The schema validates structure, not linguistic quality or
cultural authenticity.

## Tests and limits

Tests cover schema and language checks, bounded repair attempts, persistence, rejection, approval
revalidation, project registration, and the invariant that approval creates no production jobs.
SQLite's `CREATE TABLE IF NOT EXISTS` migration adds `storyboard_drafts` to an existing Phase 1 DB.
This phase does not yet provide a web review UI, reviewer identity/authentication, concurrent
review locking, or an external LLM adapter.
