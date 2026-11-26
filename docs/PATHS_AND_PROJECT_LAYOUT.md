# Shared project paths

## Rule

Use one extracted `ai_content_system` directory for every phase. Run CLI commands from
that directory and use the same `outputs/system.db` database path.

## Storyboard portability

When a storyboard is registered, the application validates it, hashes it, and copies it
to `assets/storyboards/<sha256>.json`. SQLite stores the relative path, not the original
machine-specific absolute path. The visual-production service resolves that path from
the project root derived from the database location and verifies the SHA-256 hash before
loading it.

Legacy records containing absolute paths are supported: if the original path no longer
exists, the application searches the managed storyboard folder, approved output folder,
and examples folder for a JSON file with the expected hash.

## If “Storyboard file not found” still appears

1. Confirm the terminal's current directory is the `ai_content_system` project root.
2. Confirm you are passing the same `--db outputs/system.db` to each command.
3. Confirm the registered storyboard exists in `assets/storyboards/` or `outputs/approved/`.
4. If you have multiple extracted copies, use the database and storyboard from the same
   project folder. Do not mix a project ID from one database with another database.
5. Re-register the approved storyboard if the original project record or its storyboard
   file is missing:

   ```bash
   ai-content init-project outputs/approved/the_last_coffee_ceremony.json --db outputs/system.db
   ```

The `init-project` command prints a new project ID and run ID. Use that new project ID
for Phase 3.
