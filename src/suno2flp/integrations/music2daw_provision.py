"""Explicit, isolated CLI-only provisioning. Never invokes FLP operations."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import ValidationError

from suno2flp.core.backend_models import (
    MUSIC2DAW_REPOSITORY,
    MUSIC2DAW_REVISION,
    REQUIRED_BACKEND_FILES,
    BackendProvisionRecord,
)
from suno2flp.core.errors import BackendProvisionError, TemplateInspectionError


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backend_environment(root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "NUGET_PACKAGES": str(root / "nuget"),
        "NUGET_HTTP_CACHE_PATH": str(root / "nuget-http-cache"),
        "NUGET_SCRATCH": str(root / "nuget-scratch"),
        "NUGET_PLUGINS_CACHE_PATH": str(root / "nuget-plugin-cache"),
        "DOTNET_CLI_HOME": str(root / "dotnet-home"),
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_NOLOGO": "1",
        "DOTNET_ROLL_FORWARD": "LatestPatch",
    }


def verify_backend(directory: Path) -> tuple[BackendProvisionRecord, str]:
    """Verify a local provisioning record, not its cryptographic authenticity."""
    root = directory.resolve()
    try:
        raw = (root / "backend.json").read_bytes()
        record = BackendProvisionRecord.model_validate_json(raw)
    except (OSError, ValueError, ValidationError) as exc:
        raise TemplateInspectionError("backend_manifest_invalid", str(exc)) from exc
    try:
        published = {
            p.relative_to(root).as_posix() for p in (root / "publish").rglob("*") if p.is_file()
        }
        if published != {p for p in record.files if p.startswith("publish/")}:
            raise ValueError("Published file inventory differs from provisioning record")
        for name, expected in record.files.items():
            target = root / name
            if not target.resolve().is_relative_to(root) or file_sha256(target) != expected:
                raise ValueError(f"Backend file changed or escapes installation: {name}")
    except (OSError, ValueError, RuntimeError) as exc:
        raise TemplateInspectionError("backend_integrity_failed", str(exc)) from exc
    return record, hashlib.sha256(raw).hexdigest()


def provision_music2daw(directory: Path) -> BackendProvisionRecord:
    """Build the exact reviewed source into a new private directory; preserve failures."""
    if directory.exists() or directory.is_symlink():
        raise BackendProvisionError("destination_exists", "Use a new installation directory")
    git, dotnet = shutil.which("git"), shutil.which("dotnet")
    if not git or not dotnet:
        raise BackendProvisionError("prerequisite_missing", "Git and .NET SDK 10 are required")
    root = directory.resolve()
    try:
        root.mkdir()
        environment = backend_environment(root)

        def run(args: list[str], code: str) -> str:
            try:
                result = subprocess.run(
                    args,
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise BackendProvisionError(code, str(exc)) from exc
            with (root / "provision.log").open("a", encoding="utf-8") as log:
                log.write(json.dumps(args) + "\n" + result.stdout + result.stderr + "\n")
            if result.returncode:
                raise BackendProvisionError(code, f"Command failed; see {root / 'provision.log'}")
            return result.stdout.strip()

        sdk = run([dotnet, "--version"], "sdk_unavailable")
        if not sdk.startswith("10."):
            raise BackendProvisionError("sdk_unavailable", f"Expected SDK 10; found {sdk}")
        (root / "global.json").write_text(
            json.dumps({"sdk": {"version": sdk, "rollForward": "disable"}}), encoding="utf-8"
        )
        source = root / "source"
        hooks = ["-c", f"core.hooksPath={root / 'no-hooks'}"]
        run([git, *hooks, "init", "--quiet", str(source)], "source_fetch_failed")
        prefix = [git, "-C", str(source), "-c", "core.autocrlf=false", *hooks]
        run(
            [*prefix, "fetch", "--depth", "1", MUSIC2DAW_REPOSITORY, MUSIC2DAW_REVISION],
            "source_fetch_failed",
        )
        run([*prefix, "checkout", "--detach", "FETCH_HEAD"], "source_checkout_failed")
        if run([*prefix, "rev-parse", "HEAD"], "source_checkout_failed") != MUSIC2DAW_REVISION:
            raise BackendProvisionError(
                "source_revision_mismatch", "Checkout is not the reviewed pin"
            )
        project = str(source / "src/Music2Daw.Cli/Music2Daw.Cli.csproj")
        run(
            [
                dotnet,
                "restore",
                project,
                "--use-lock-file",
                "--packages",
                str(root / "nuget"),
                "--source",
                "https://api.nuget.org/v3/index.json",
            ],
            "restore_failed",
        )
        run(
            [
                dotnet,
                "publish",
                project,
                "--no-restore",
                "--configuration",
                "Release",
                "--no-self-contained",
                "-p:UseAppHost=false",
                "--output",
                str(root / "publish"),
            ],
            "build_failed",
        )
        if run(
            [*prefix, "status", "--porcelain", "--untracked-files=no"], "source_checkout_failed"
        ):
            raise BackendProvisionError(
                "source_changed", "Tracked upstream source changed during build"
            )
        assets = json.loads(
            (source / "src/Music2Daw.Cli/obj/project.assets.json").read_text(encoding="utf-8-sig")
        )
        packages = {
            name.rsplit("/", 1)[0]: name.rsplit("/", 1)[1]
            for name, item in assets["libraries"].items()
            if item["type"] == "package"
        }
        names = set(REQUIRED_BACKEND_FILES)
        names.update(
            p.relative_to(root).as_posix() for p in (root / "publish").rglob("*") if p.is_file()
        )
        names.add("source/src/Music2Daw.Cli/obj/project.assets.json")
        record = BackendProvisionRecord(
            schema_version=1,
            backend="music2daw",
            repository=MUSIC2DAW_REPOSITORY,
            revision=MUSIC2DAW_REVISION,
            license="GPL-3.0-or-later",
            sdk_version=sdk,
            packages=packages,
            files={name: file_sha256(root / name) for name in sorted(names)},
        )
        with (root / "backend.json").open("x", encoding="utf-8") as stream:
            stream.write(record.model_dump_json(indent=2) + "\n")
        return record
    except BackendProvisionError:
        raise
    except (OSError, ValueError, KeyError, RuntimeError, ValidationError) as exc:
        raise BackendProvisionError("provision_failed", str(exc)) from exc
