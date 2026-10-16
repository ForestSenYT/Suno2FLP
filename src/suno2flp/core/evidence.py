"""Canonical model fingerprints shared by evidence contracts and pure services."""

import hashlib
import json

from pydantic import BaseModel


def snapshot_sha256(model: BaseModel) -> str:
    raw = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
