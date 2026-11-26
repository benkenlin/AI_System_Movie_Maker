"""Stable content-addressed hashing for pipeline inputs and artifacts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Serialize JSON-compatible values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_key(*, stage: str, inputs: dict[str, Any], model: str | None = None,
                 model_version: str | None = None,
                 config: dict[str, Any] | None = None,
                 subject_id: str = "project") -> str:
    """Cache key includes all inputs that can affect a stage's output."""
    return sha256_json({"key_version": 1, "stage": stage, "subject_id": subject_id, "inputs": inputs,
                        "model": model, "model_version": model_version,
                        "config": config or {}})
