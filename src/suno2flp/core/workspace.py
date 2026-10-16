"""Workspace creation and path guards shared by CLI and validation."""

import re
from pathlib import Path

import yaml

from suno2flp.core.config import ProjectConfig
from suno2flp.core.errors import UnsafePathError

_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def workspace_path(root: Path, relative: Path) -> Path:
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise UnsafePathError(f"Path escapes the workspace: {relative}")
    return resolved


def init_project(parent: Path, name: str) -> Path:
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name)
        or name.endswith(".")
        or name.split(".")[0].upper() in _RESERVED
    ):
        raise UnsafePathError(
            "Use a simple project name without separators or reserved device names"
        )
    parent = parent.resolve()
    if not parent.is_dir():
        raise UnsafePathError(f"Parent directory does not exist: {parent}")
    target = parent / name
    try:
        target.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise UnsafePathError(f"Refusing existing destination: {target}") from exc
    for folder in ("input", "intermediate", "output"):
        (target / folder).mkdir()
    config = ProjectConfig(name=name)
    with (target / "project.yaml").open("x", encoding="utf-8") as stream:
        yaml.safe_dump(config.model_dump(mode="json"), stream, sort_keys=False)
    return target
