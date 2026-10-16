"""Offline manual-evidence contracts; no record can grant writer eligibility."""

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from suno2flp.core.models import Contract, Diagnostic

Probe = Literal[
    "default-grow",
    "fixed-sentinel-grow",
    "explicit-grow",
    "explicit-short",
    "explicit-odd",
    "explicit-grow-notes",
]
PROBES: tuple[Probe, ...] = (
    "default-grow",
    "fixed-sentinel-grow",
    "explicit-grow",
    "explicit-short",
    "explicit-odd",
    "explicit-grow-notes",
)
StageName = Literal[
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
STAGES: tuple[StageName, ...] = (
    "identity",
    "open",
    "view_zoom",
    "save_a",
    "reopen_a",
    "resize_b",
    "reopen_b",
    "readback",
    "protection",
)
StageStatus = Literal[
    "pending_not_performed",
    "pass_observed",
    "fail_observed",
    "blocked",
    "skipped",
]
HOST_VERSION = "26.1.7.5654"
REQUIRED_EVIDENCE: dict[StageName, tuple[str, ...]] = {
    "identity": ("identity_check",),
    "open": ("observation",),
    "view_zoom": ("before", "after"),
    "save_a": ("save_observation",),
    "reopen_a": ("reopen_observation", "listening_note"),
    "resize_b": ("before", "after", "save_observation"),
    "reopen_b": ("reopen_observation", "listening_note"),
    "readback": ("input_readback", "a_readback", "b_readback", "comparison"),
    "protection": ("identity_check",),
}
HostStatus = Literal["pending_not_performed", "incomplete", "reported_complete"]


class ManualFile(Contract):
    path: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
    size_bytes: int = Field(ge=0, strict=True)
    mtime_ns: int | None = Field(default=None, ge=0, strict=True)

    @field_validator("path")
    @classmethod
    def portable_relative(cls, value: str) -> str:
        reserved = {"CON", "PRN", "AUX", "NUL"} | {
            f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
        }
        if not value or PurePosixPath(value).is_absolute() or "\\" in value:
            raise ValueError("Use a contained relative POSIX file path")
        for part in value.split("/"):
            if (
                not part
                or part in {".", ".."}
                or part.endswith((".", " "))
                or any(char in part for char in ':*?"<>|')
                or any(ord(char) < 32 for char in part)
                or part.split(".")[0].upper() in reserved
            ):
                raise ValueError("Ambiguous or escaping file path")
        return value


class ManualStage(Contract):
    status: StageStatus
    performed_at: AwareDatetime | None = None
    details: str | None = None
    reason: str | None = None
    evidence: dict[str, ManualFile] = Field(default_factory=dict)


class ManualProbeRecord(Contract):
    schema_version: Literal[1]
    probe: Probe
    operator: str | None = None
    actual_version: str | None = None
    stages: dict[StageName, ManualStage]
    outputs: dict[Literal["A", "B"], ManualFile | None] = Field(default_factory=dict)
    listening: dict[
        Literal["A", "B"],
        Literal["not_listened", "heard_as_recorded", "audible_mismatch", "unable_to_judge"],
    ] = Field(default_factory=dict)
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
    host_compatibility: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def all_stages(self) -> "ManualProbeRecord":
        if set(self.stages) != set(STAGES):
            raise ValueError("All nine stages must be explicit, including pending stages")
        return self


class ManualEntry(Contract):
    probe: Probe
    record: ManualFile
    form: ManualFile
    candidate: ManualFile


class ManualRecordManifest(Contract):
    schema_version: Literal[1]
    profile: Literal["fl26-26.1.7.5654-manual-v1"]
    protected_files: list[ManualFile] = Field(min_length=1)
    provenance_files: list[ManualFile] = Field(min_length=1)
    records: list[ManualEntry]

    @model_validator(mode="after")
    def six_distinct_probes(self) -> "ManualRecordManifest":
        if len(self.records) != 6 or {entry.probe for entry in self.records} != set(PROBES):
            raise ValueError("Exactly one entry for each of the six probes is required")
        paths = [
            ref.path.casefold()
            for entry in self.records
            for ref in (entry.record, entry.form, entry.candidate)
        ]
        if len(set(paths)) != len(paths):
            raise ValueError("Records, forms and candidates must have distinct file paths")
        return self


class ManualFileCheck(Contract):
    role: str
    expected: ManualFile
    actual_sha256: str | None = None
    actual_size_bytes: int | None = None
    actual_mtime_ns: int | None = None
    valid: bool = False


class ManualRecordSummary(Contract):
    probe: Probe
    host_status: HostStatus = "incomplete"
    pending_stages: int = 0
    stage_counts: dict[str, int] = Field(default_factory=dict)
    next_required_evidence: dict[str, list[str]] = Field(default_factory=dict)


class ManualRecordReport(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: str | None = None
    integrity_valid: bool = False
    host_status: HostStatus = "incomplete"
    records: list[ManualRecordSummary] = Field(default_factory=list)
    stage_counts: dict[str, int] = Field(default_factory=dict)
    unknown_stages: int = 54
    files: list[ManualFileCheck] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
    host_compatibility: Literal["unverified"] = "unverified"
