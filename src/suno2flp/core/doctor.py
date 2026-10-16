"""Non-invasive prerequisite inventory. Presence is distinct from connectivity."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from suno2flp.core.models import Contract


class EnvironmentCheck(Contract):
    component: str
    status: Literal["available", "unavailable", "unverified"]
    detail: str


def _probe(component: str, command: str, flag: str = "--version") -> EnvironmentCheck:
    executable = shutil.which(command)
    if executable is None:
        return EnvironmentCheck(
            component=component, status="unavailable", detail="Not found on PATH"
        )
    try:
        result = subprocess.run(
            [executable, flag],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (result.stdout or result.stderr).strip()
        if command == "dotnet" and flag == "--list-sdks" and not output:
            return EnvironmentCheck(
                component=component, status="unavailable", detail="No .NET SDKs installed"
            )
        return EnvironmentCheck(
            component=component,
            status="available" if result.returncode == 0 else "unverified",
            detail=output.splitlines()[0] if output else str(executable),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return EnvironmentCheck(component=component, status="unverified", detail=str(exc))


def check_environment() -> list[EnvironmentCheck]:
    checks = [
        EnvironmentCheck(
            component="Python",
            status="available" if sys.version_info >= (3, 11) else "unavailable",
            detail=f"{sys.version.split()[0]} ({sys.executable})",
        )
    ]
    for component, executable, flag in (
        ("Git", "git", "--version"),
        ("FFmpeg", "ffmpeg", "-version"),
        (".NET SDK (Music2DAW needs 10)", "dotnet", "--list-sdks"),
        ("uv", "uv", "--version"),
        ("Git LFS (optional)", "git-lfs", "version"),
    ):
        checks.append(_probe(component, executable, flag))
    for component, command in (("Claude Code", "claude"), ("Codex", "codex")):
        path = shutil.which(command)
        checks.append(
            EnvironmentCheck(
                component=component,
                status="available" if path else "unavailable",
                detail=f"Executable located: {path}; authentication unverified"
                if path
                else "Not on PATH",
            )
        )
    candidates = [
        Path(value)
        for name in ("ProgramFiles", "ProgramFiles(x86)")
        if (value := os.environ.get(name))
    ]
    found: list[Path] = []
    for parent in candidates:
        try:
            found.extend((parent / "Image-Line").glob("FL Studio*/FL*.exe"))
        except OSError:
            continue
    checks.append(
        EnvironmentCheck(
            component="FL Studio",
            status="available" if found else "unverified",
            detail=f"Installation candidate: {found[0]}; launch/version unverified"
            if found
            else "Not found in standard Windows locations; custom installations may exist",
        )
    )
    checks.append(
        EnvironmentCheck(
            component="FLP backends / MCP / virtual MIDI ports",
            status="unverified",
            detail="No connection attempted; backend handshake and tool discovery required",
        )
    )
    return checks
