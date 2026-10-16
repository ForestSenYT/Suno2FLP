"""Explicit restricted-writer contracts, separate from permanently blocked previews."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from suno2flp.core.assessment_models import LocalBindingCheck
from suno2flp.core.backend_models import SHA256, TemplateInspectionReport
from suno2flp.core.build_models import TemplateBindingDocument
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.models import Arrangement, Contract, Diagnostic

ReferenceKind = Literal["synthetic_fixture", "operator_host_readback", "unverified"]


class WriterTargetReview(Contract):
    binding_index: int = Field(ge=0, strict=True)
    note_index: int = Field(ge=0, strict=True)
    clip_index: int = Field(ge=0, strict=True)
    note_sha256: SHA256
    clip_sha256: SHA256
    generator_event_index: int = Field(ge=0, strict=True)
    generator_name: str = Field(min_length=1)


class Fl26WriterPolicy(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["fl26-26.1.7.5654-write-v1"]
    template_sha256: SHA256
    inventory_snapshot_sha256: SHA256
    bindings_snapshot_sha256: SHA256
    reference_kind: ReferenceKind
    reviewer: str = Field(min_length=1)
    reference_evidence: str = Field(min_length=1)
    dependency_review: Literal["attested", "unverified"]
    instrument_review: Literal["attested", "unverified"]
    local_use_review: Literal["attested", "unverified"]
    content_policy: Literal["replace_all_bound_notes_and_clips"]
    note_attribute_policy: Literal["preserve_reviewed_prototype"]
    clip_extension_policy: Literal["preserve_exact_reference_bytes"]
    targets: list[WriterTargetReview]

    @model_validator(mode="after")
    def unique_targets(self) -> "Fl26WriterPolicy":
        for field in ("binding_index", "note_index", "clip_index"):
            values = [getattr(t, field) for t in self.targets]
            if len(set(values)) != len(values):
                raise ValueError("Writer policy cannot share prototype targets")
        return self


class WriterPolicyDocument(Contract):
    config: Fl26WriterPolicy
    source_path: Path | None = None
    source_sha256: SHA256 | None = None


class Fl26WriteIntent(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["fl26-26.1.7.5654-write-v1"] = "fl26-26.1.7.5654-write-v1"
    status: Literal["ready", "blocked"]
    compatibility: Literal["unverified"] = "unverified"
    reference_kind: ReferenceKind
    arrangement: Arrangement
    inspection: TemplateInspectionReport
    bindings: TemplateBindingDocument
    policy: WriterPolicyDocument
    binding_check: LocalBindingCheck
    tempo_millibpm: int | None = Field(default=None, ge=1, le=999000)
    edit_event_indices: list[int]
    diagnostics: list[Diagnostic]
    inputs_snapshot_sha256: dict[str, SHA256]

    @model_validator(mode="after")
    def honest_intent(self) -> "Fl26WriteIntent":
        expected = {
            name: snapshot_sha256(getattr(self, name))
            for name in ("arrangement", "inspection", "bindings", "policy")
        }
        if (
            self.inputs_snapshot_sha256 != expected
            or self.reference_kind != self.policy.config.reference_kind
        ):
            raise ValueError("Writer intent snapshot provenance disagrees")
        if self.status != (
            "blocked" if any(d.severity == "error" for d in self.diagnostics) else "ready"
        ):
            raise ValueError("Writer intent status must reflect blocking diagnostics")
        return self


class WriterInputFile(Contract):
    kind: Literal["arrangement", "inspection", "bindings", "policy", "source_midi", "template"]
    path: Path
    sha256: SHA256
    size_bytes: int = Field(ge=0)
    mtime_ns: int


class Fl26WritePreparation(Contract):
    intent: Fl26WriteIntent
    input_files: list[WriterInputFile]


class Fl26Verification(Contract):
    schema_version: Literal[1] = 1
    level: Literal["structural_round_trip_only"] = "structural_round_trip_only"
    compatibility: Literal["unverified"] = "unverified"
    template_sha256: SHA256
    output_sha256: SHA256
    note_count: int = Field(ge=1)
    clip_count: int = Field(ge=1)
    changed_event_indices: list[int]
    preserved_event_sha256: dict[int, SHA256]


class WriterBundleProvenance(Contract):
    schema_version: Literal[1] = 1
    compatibility: Literal["unverified"] = "unverified"
    intent: Fl26WriteIntent
    input_files: list[WriterInputFile]
    verification: Fl26Verification
