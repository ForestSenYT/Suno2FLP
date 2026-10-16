"""Hash-verified read-only inspection through the isolated Music2DAW CLI."""

import hashlib
import re
import shutil
import struct
import subprocess
from pathlib import Path

from pydantic import ValidationError

from suno2flp.core.backend_models import FlpHeader, Music2DawSummary, TemplateInspectionReport
from suno2flp.core.errors import TemplateInspectionError
from suno2flp.core.models import Diagnostic
from suno2flp.core.template_profiles import FL26_READ_PROFILE
from suno2flp.core.template_summary import compare_backend_summary
from suno2flp.integrations.music2daw_provision import (
    backend_environment,
    file_sha256,
    verify_backend,
)
from suno2flp.integrations.template_inventory import scan_template_inventory


class Music2DawInspector:
    def __init__(self, backend_directory: Path, *, timeout: float = 30):
        if not 0 < timeout <= 300:
            raise ValueError("Inspection timeout must be positive and at most 300 seconds")
        self.directory = backend_directory.resolve()
        self.timeout = timeout

    def inspect(self, template: Path) -> TemplateInspectionReport:
        record, record_hash = verify_backend(self.directory)
        try:
            path = template.resolve()
            raw = path.read_bytes()
        except (OSError, RuntimeError) as exc:
            raise TemplateInspectionError("template_unreadable", str(exc)) from exc
        try:
            if path.suffix.lower() != ".flp" or len(raw) < 22 or raw[:4] != b"FLhd":
                raise ValueError("Expected an existing .flp project with FLhd header")
            length, format_id, channels, ppq = struct.unpack_from("<IHHH", raw, 4)
            if length != 6:
                raise ValueError("Unsupported FLhd length")
            header = FlpHeader(format=format_id, channel_count=channels, ppq=ppq)
        except (ValueError, struct.error, ValidationError) as exc:
            raise TemplateInspectionError("template_invalid", str(exc)) from exc
        before = hashlib.sha256(raw).hexdigest()
        inventory = scan_template_inventory(raw)
        dotnet = shutil.which("dotnet")
        if not dotnet:
            raise TemplateInspectionError("dotnet_missing", ".NET 10 runtime was not found on PATH")
        environment = backend_environment(self.directory)

        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            try:
                return subprocess.run(
                    args,
                    cwd=self.directory / "publish",
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    timeout=self.timeout,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except subprocess.TimeoutExpired as exc:
                raise TemplateInspectionError(
                    "backend_timeout", "Read-only process timed out"
                ) from exc
            except (OSError, UnicodeError) as exc:
                raise TemplateInspectionError("backend_process_failed", str(exc)) from exc

        runtime = run([dotnet, "--list-runtimes"])
        versions = re.findall(
            r"^Microsoft\.NETCore\.App (10\.0\.\d+)\s", runtime.stdout, re.MULTILINE
        )
        if runtime.returncode or not versions:
            raise TemplateInspectionError(
                "dotnet_runtime_missing", "Microsoft.NETCore.App 10.0 is required"
            )
        runtime_version = max(versions, key=lambda value: tuple(map(int, value.split("."))))
        try:
            result = run(
                [dotnet, str(self.directory / "publish/music2daw.dll"), "inspect", str(path)]
            )
        finally:
            try:
                unchanged = file_sha256(path) == before
            except OSError:
                unchanged = False
            if not unchanged:
                raise TemplateInspectionError(
                    "template_changed", "Template changed during inspection"
                )
            _, after_record_hash = verify_backend(self.directory)
            if after_record_hash != record_hash:
                raise TemplateInspectionError(
                    "backend_integrity_failed", "Provisioning record changed"
                )
        if result.returncode:
            raise TemplateInspectionError(
                "backend_process_failed",
                result.stderr.strip()[:2000] or f"Exit {result.returncode}",
            )
        try:
            project = Music2DawSummary.model_validate_json(result.stdout)
            if project.source_path.resolve() != path or project.ppq != ppq:
                raise ValueError("Returned source path or PPQ differs from inspected input")
            if len(project.channels) != header.channel_count:
                raise ValueError("Returned channel count differs from FLhd")
        except (ValueError, RuntimeError, ValidationError) as exc:
            raise TemplateInspectionError("backend_output_invalid", str(exc)) from exc
        local, summary_status, mismatches = compare_backend_summary(inventory, project)
        extra_diagnostics = []
        if summary_status == "inconsistent":
            extra_diagnostics.append(
                Diagnostic(
                    code="backend_summary_inconsistent",
                    severity="warning",
                    path=path,
                    message="Backend summary disagrees with selected byte inventory; "
                    "retain both as evidence and do not trust the backend's successful exit",
                )
            )
        if inventory.profile_id == FL26_READ_PROFILE.identifier:
            extra_diagnostics.append(
                Diagnostic(
                    code="fl26_read_only_profile",
                    severity="warning",
                    path=path,
                    message="Exact-build FL26 byte reading only; backend writer, opaque semantics "
                    "and FL Studio playback compatibility remain unverified",
                )
            )
        return TemplateInspectionReport(
            template_path=path,
            size_bytes=len(raw),
            template_sha256_before=before,
            template_sha256_after=before,
            backend_manifest_sha256=record_hash,
            backend=record,
            runtime_version=runtime_version,
            header=header,
            project=project,
            inventory=inventory,
            local_summary=local,
            backend_summary_status=summary_status,
            backend_summary_mismatches=mismatches,
            diagnostics=[
                Diagnostic(code=code, severity="warning", message=message, path=path)
                for code, message in [
                    (
                        "fl_studio_compatibility_unverified",
                        "Parser inspection does not verify FL Studio opening or playback",
                    ),
                    (
                        "plugin_availability_unverified",
                        "Plugin/sample names and state hashes do not verify "
                        "local availability or licensing",
                    ),
                    (
                        "template_rights_unverified",
                        "Template ownership and redistribution rights were not verified",
                    ),
                    (
                        "template_semantics_unverified",
                        "Byte-linked inventory and backend summary do not verify "
                        "all event semantics, plugin automation or writer eligibility",
                    ),
                ]
            ]
            + extra_diagnostics,
        )
