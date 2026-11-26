
from __future__ import annotations

import json
from pathlib import Path
from pydantic import ValidationError

from .models import Storyboard


class StoryboardValidationError(Exception):
    """Raised when a storyboard cannot be loaded or does not satisfy the contract."""


def load_storyboard(path: str | Path) -> Storyboard:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StoryboardValidationError(f"Storyboard file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise StoryboardValidationError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    try:
        return Storyboard.model_validate(raw)
    except ValidationError as exc:
        details = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "<root>"
            details.append(f"- {location}: {error['msg']}")
        raise StoryboardValidationError(
            "Storyboard failed validation:\n" + "\n".join(details)
        ) from exc


def export_json_schema(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema = Storyboard.model_json_schema()
    destination.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination
