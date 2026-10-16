"""Original local record fixtures; no real project or backend data is used."""

import hashlib
import json
from pathlib import Path

PROBES = [
    "default-grow",
    "fixed-sentinel-grow",
    "explicit-grow",
    "explicit-short",
    "explicit-odd",
    "explicit-grow-notes",
]
STAGES = [
    "identity",
    "open",
    "view_zoom",
    "save_a",
    "reopen_a",
    "resize_b",
    "reopen_b",
    "readback",
    "protection",
]
REQUIRED = {
    "identity": ["identity_check"],
    "open": ["observation"],
    "view_zoom": ["before", "after"],
    "save_a": ["save_observation"],
    "reopen_a": ["reopen_observation", "listening_note"],
    "resize_b": ["before", "after", "save_observation"],
    "reopen_b": ["reopen_observation", "listening_note"],
    "readback": ["input_readback", "a_readback", "b_readback", "comparison"],
    "protection": ["identity_check"],
}


def save(path: Path, content: bytes) -> dict:
    path.write_bytes(content)
    return {
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def json_file(root: Path, name: str, data: dict) -> dict:
    return save(root / name, (json.dumps(data, indent=2) + "\n").encode())


def make_record_set(tmp_path):
    manifest = {
        "schema_version": 1,
        "profile": "fl26-26.1.7.5654-manual-v1",
        "protected_files": [save(tmp_path / "original.flp", b"original synthetic bytes")],
        "provenance_files": [save(tmp_path / "origin.txt", b"authored synthetic origin")],
        "records": [],
    }
    records = []
    for name in PROBES:
        data = {
            "schema_version": 1,
            "probe": name,
            "stages": {key: {"status": "pending_not_performed"} for key in STAGES},
        }
        records.append(data)
        manifest["records"].append(
            {
                "probe": name,
                "record": json_file(tmp_path, name + ".json", data),
                "form": save(tmp_path / (name + ".md"), b"Original blank human form\n"),
                "candidate": save(tmp_path / (name + ".flp"), ("synthetic " + name).encode()),
            }
        )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, path, manifest, records
