"""Read-only FL26 evidence; no field in this contract authorizes an FLP write."""

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from suno2flp.core.backend_models import SHA256, TemplateInspectionReport
from suno2flp.core.build_models import (
    PlanInputFile,
    PlannedBindingPart,
    SourceSelector,
    TemplateBindingDocument,
)
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.models import Arrangement, Contract, Diagnostic

DEPENDENCY_EVENTS = {
    192: "display_name",
    196: "sample_reference",
    201: "generator_declaration",
    203: "display_name",
    212: "plugin_initialization",
    213: "plugin_state",
}


class DependencyEvidence(Contract):
    event_index: int = Field(ge=0)
    event_id: int
    kind: Literal[
        "display_name",
        "sample_reference",
        "generator_declaration",
        "plugin_initialization",
        "plugin_state",
    ]
    file_offset: int = Field(ge=0)
    payload_size: int = Field(ge=0)
    payload_sha256: SHA256
    channel_context: int | None = Field(default=None, ge=0)
    owner_verified: Literal[False] = False
    text: str | None = None
    text_status: Literal["decoded", "empty", "invalid", "not_applicable"]
    raw_text_hex: str | None = None
    version: None = None
    format: None = None
    external_file_sha256: None = None
    availability: Literal["unverified"] = "unverified"
    rights: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def consistent_text(self) -> "DependencyEvidence":
        if DEPENDENCY_EVENTS.get(self.event_id) != self.kind:
            raise ValueError("Dependency kind differs from assessed event ID")
        if self.event_id in {212, 213}:
            if (
                self.raw_text_hex is not None
                or self.text is not None
                or self.text_status != "not_applicable"
            ):
                raise ValueError("Opaque plugin state must not be interpreted as text")
        else:
            if self.raw_text_hex is None:
                raise ValueError("Text evidence must retain raw bytes")
            raw = bytes.fromhex(self.raw_text_hex)
            if (
                len(raw) != self.payload_size
                or hashlib.sha256(raw).hexdigest() != self.payload_sha256
            ):
                raise ValueError("Text bytes differ from payload evidence")
            try:
                text = raw.decode("utf-16-le").removesuffix("\0")
                status = "decoded" if text else "empty"
            except UnicodeError:
                text, status = None, "invalid"
            if self.text != text or self.text_status != status:
                raise ValueError("Decoded text differs from retained bytes")
        return self


class CompatibilityFinding(Contract):
    code: str
    message: str
    event_indices: list[int] = Field(default_factory=list)
    note_indices: list[int] = Field(default_factory=list)
    clip_indices: list[int] = Field(default_factory=list)


class WriterGate(Contract):
    gate: str
    status: Literal["blocked", "unverified"]
    reason: str


class LocalBindingCheck(Contract):
    basis: Literal["local_byte_inventory_only"] = "local_byte_inventory_only"
    status: Literal["matched", "blocked"]
    instrument_intent: Literal["unverified"] = "unverified"
    arrangement: Arrangement
    bindings: TemplateBindingDocument
    arrangement_snapshot_sha256: SHA256
    parts: list[PlannedBindingPart]
    unbound_sources: list[SourceSelector]
    diagnostics: list[Diagnostic]

    @model_validator(mode="after")
    def honest_snapshot(self) -> "LocalBindingCheck":
        if snapshot_sha256(self.arrangement) != self.arrangement_snapshot_sha256:
            raise ValueError("Arrangement snapshot hash differs from retained source evidence")
        expected = "blocked" if any(d.severity == "error" for d in self.diagnostics) else "matched"
        if self.status != expected:
            raise ValueError("Binding status must reflect blocking diagnostics")
        return self


class TemplateReadinessReport(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["fl26-readiness-v1"] = "fl26-readiness-v1"
    writer_status: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
    compatibility: Literal["unverified"] = "unverified"
    dependency_scope: Literal["selected_declarations_only"] = "selected_declarations_only"
    inspection: TemplateInspectionReport
    inspection_snapshot_sha256: SHA256
    dependencies: list[DependencyEvidence]
    findings: list[CompatibilityFinding]
    writer_gates: list[WriterGate]
    binding_check: LocalBindingCheck | None = None
    input_files: list[PlanInputFile] = Field(default_factory=list)
    template_mtime_ns_before: int | None = None
    template_mtime_ns_after: int | None = None

    @model_validator(mode="after")
    def dependency_links(self) -> "TemplateReadinessReport":
        if snapshot_sha256(self.inspection) != self.inspection_snapshot_sha256:
            raise ValueError("Inspection snapshot hash differs from retained evidence")
        inventory = self.inspection.inventory
        if inventory is None:
            raise ValueError("Readiness requires retained inventory")
        expected = [e for e in inventory.events if e.event_id in DEPENDENCY_EVENTS]
        if len(expected) != len(self.dependencies):
            raise ValueError("Selected dependency declarations must be complete")
        for event, dependency in zip(expected, self.dependencies, strict=True):
            if (
                event.event_index,
                event.event_id,
                event.payload_offset,
                event.payload_size,
                event.payload_sha256,
            ) != (
                dependency.event_index,
                dependency.event_id,
                dependency.file_offset,
                dependency.payload_size,
                dependency.payload_sha256,
            ):
                raise ValueError("Dependency source link differs from retained inventory")
        return self
