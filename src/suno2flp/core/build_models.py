"""Explicit source/template bindings and non-executable planning evidence."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from suno2flp.core.backend_models import SHA256, TemplateInspectionReport
from suno2flp.core.models import Arrangement, ArrangementNoteOrigin, Contract, Diagnostic


class SourceSelector(Contract):
    source_input: int = Field(ge=0, strict=True)
    source_track_position: int = Field(ge=0, strict=True)
    source_channel: int = Field(ge=0, le=15, strict=True)


class TemplateBindingRule(SourceSelector):
    template_channel_id: int = Field(ge=0, le=255, strict=True)
    template_pattern_id: int = Field(ge=0, le=65534, strict=True)
    template_playlist_track: int = Field(ge=0, le=499, strict=True)


class TemplateBindingConfig(Contract):
    schema_version: Literal[1] = 1
    template_sha256: SHA256
    backend_revision: Literal["6def9463d6fa8636bbc81010581318a39c47d3c4"]
    bindings: list[TemplateBindingRule]

    @model_validator(mode="after")
    def one_to_one(self) -> "TemplateBindingConfig":
        sources = [
            (b.source_input, b.source_track_position, b.source_channel) for b in self.bindings
        ]
        targets = [
            [b.template_channel_id for b in self.bindings],
            [b.template_pattern_id for b in self.bindings],
            [b.template_playlist_track for b in self.bindings],
        ]
        if len(set(sources)) != len(sources) or any(len(set(t)) != len(t) for t in targets):
            raise ValueError(
                "Bindings must be one-to-one for source, channel, Pattern and playlist track"
            )
        return self


class TemplateBindingDocument(Contract):
    config: TemplateBindingConfig
    source_path: Path | None = None
    source_sha256: SHA256 | None = None


class PlanInputFile(Contract):
    kind: Literal["arrangement", "inspection", "bindings"]
    path: Path
    sha256: SHA256


class PlannedNote(Contract):
    arrangement_note_index: int = Field(ge=0)
    origin: ArrangementNoteOrigin
    source_channel: int = Field(ge=0, le=15)
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(ge=1, le=127)
    start_tick: int = Field(ge=0, le=2147483647)
    duration_ticks: int = Field(ge=1, le=2147483647)


class PlannedBindingPart(Contract):
    binding_index: int = Field(ge=0)
    arrangement_track_index: int = Field(ge=0)
    binding: TemplateBindingRule
    clip_start_tick: Literal[0] = 0
    clip_length_ticks: int | None = Field(default=None, ge=1, le=2147483647)
    notes: list[PlannedNote] | None = None
    template_note_indices: list[int] = Field(default_factory=list)
    template_clip_indices: list[int] = Field(default_factory=list)


class DryRunBuildPlan(Contract):
    schema_version: Literal[1] = 1
    algorithm_version: Literal[1, 2] = 2
    capability_profile: Literal[
        "music2daw-6def9463-dry-run-v1", "music2daw-6def9463-dry-run-v2"
    ] = "music2daw-6def9463-dry-run-v2"
    status: Literal["blocked", "review_required"]
    execution_allowed: Literal[False] = False
    compatibility: Literal["unverified"] = "unverified"
    arrangement: Arrangement
    inspection: TemplateInspectionReport
    bindings: TemplateBindingDocument
    arrangement_snapshot_sha256: SHA256
    inspection_snapshot_sha256: SHA256
    inventory_snapshot_sha256: SHA256 | None = None
    input_files: list[PlanInputFile] = Field(default_factory=list)
    target_ppq: int = Field(ge=1, le=32767)
    tempo_millibpm: int | None = Field(default=None, ge=1, le=999000)
    parts: list[PlannedBindingPart]
    unbound_sources: list[SourceSelector]
    diagnostics: list[Diagnostic]

    @model_validator(mode="after")
    def honest_status(self) -> "DryRunBuildPlan":
        expected = (
            "blocked" if any(d.severity == "error" for d in self.diagnostics) else "review_required"
        )
        if self.status != expected:
            raise ValueError("Plan status must reflect blocking diagnostics")
        if not self.capability_profile.endswith(f"-v{self.algorithm_version}"):
            raise ValueError("Capability profile must match the planning algorithm version")
        return self
