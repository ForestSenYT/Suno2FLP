"""Current-file evidence and structural quality, separate from writer policy."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from suno2flp.core.models import ArrangementOptions, Contract, Diagnostic


class FileIdentity(Contract):
    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0, strict=True)
    mtime_ns: int = Field(ge=0, strict=True)


class ArrangementQualityReport(Contract):
    schema_version: Literal[1] = 1
    valid: bool = False
    source_count: int = 0
    track_count: int = 0
    note_count: int = 0
    event_count: int = 0
    arrangement_fingerprint: str | None = None
    reference_fingerprint: str | None = None
    input_files: list[FileIdentity] = Field(default_factory=list)
    referenced_paths: list[Path] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False


class PreparationRun(Contract):
    schema_version: Literal[1] = 1
    algorithm_version: Literal[1] = 1
    project_root: Path
    destination: Path
    options: ArrangementOptions
    mapping_file: Path | None = None
    input_files: list[FileIdentity]
    artifacts: dict[str, FileIdentity]
    status: Literal["offline_ready"] = "offline_ready"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
