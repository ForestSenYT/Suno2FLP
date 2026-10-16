"""Versioned cross-module contracts; all musical positions use integer MIDI ticks."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Diagnostic(Contract):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    path: Path | None = None
    track_index: int | None = Field(default=None, ge=0)
    event_index: int | None = Field(default=None, ge=0)
    source_input: int | None = Field(default=None, ge=0)


class AudioMetadata(Contract):
    channels: int = Field(gt=0)
    sample_rate: int = Field(gt=0)
    frames: int = Field(ge=0)
    sample_width_bytes: int = Field(gt=0)
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)


class MidiMetadata(Contract):
    format: Literal[0, 1, 2]
    tracks: int = Field(ge=0)
    ticks_per_beat: int = Field(gt=0)
    note_events: int = Field(ge=0)


class Asset(Contract):
    path: Path  # Relative to AssetManifest.root.
    kind: Literal["midi", "wav"]
    size_bytes: int = Field(ge=0)
    midi: MidiMetadata | None = None
    audio: AudioMetadata | None = None

    @model_validator(mode="after")
    def consistent_metadata(self) -> "Asset":
        if self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError("Asset paths must be relative to the manifest root")
        if (self.kind == "midi" and self.audio) or (self.kind == "wav" and self.midi):
            raise ValueError("Metadata must match the asset kind")
        return self


class AssetMatch(Contract):
    midi_path: Path
    audio_path: Path
    method: Literal["unique_filename"] = "unique_filename"


class AssetManifest(Contract):
    schema_version: Literal[1] = 1
    root: Path
    assets: list[Asset] = Field(default_factory=list)
    matches: list[AssetMatch] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class MidiNote(Contract):
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(ge=0, le=127)
    channel: int = Field(default=0, ge=0, le=15)
    start_tick: int = Field(ge=0)
    duration_ticks: int = Field(ge=0)
    original_start_tick: int | None = Field(default=None, ge=0)
    original_duration_ticks: int | None = Field(default=None, ge=0)
    note_on_event_index: int | None = Field(default=None, ge=0)
    note_off_event_index: int | None = Field(default=None, ge=0)


class TempoEvent(Contract):
    tick: int = Field(ge=0)
    microseconds_per_beat: int = Field(gt=0)
    source_track: int | None = Field(default=None, ge=0)
    source_event: int | None = Field(default=None, ge=0)
    source_input: int | None = Field(default=None, ge=0)
    is_default: bool = False


class MeterEvent(Contract):
    tick: int = Field(ge=0)
    numerator: int = Field(gt=0)
    denominator: int = Field(default=4, ge=1, le=2**255)
    clocks_per_click: int = Field(default=24, ge=0, le=255)
    notated_32nd_notes_per_beat: int = Field(default=8, ge=0, le=255)
    source_track: int | None = Field(default=None, ge=0)
    source_event: int | None = Field(default=None, ge=0)
    source_input: int | None = Field(default=None, ge=0)
    is_default: bool = False

    @field_validator("denominator")
    @classmethod
    def power_of_two(cls, value: int) -> int:
        if value & (value - 1):
            raise ValueError("MIDI meter denominator must be a power of two")
        return value


class MidiEvent(Contract):
    """An original decoded SMF message, retaining track-local order and delta ticks."""

    event_index: int = Field(ge=0)
    delta_ticks: int = Field(ge=0)
    tick: int = Field(ge=0)
    message: dict[str, JsonValue]


class MidiTrack(Contract):
    name: str
    index: int | None = Field(default=None, ge=0)
    end_tick: int = Field(default=0, ge=0)
    notes: list[MidiNote] = Field(default_factory=list)
    events: list[MidiEvent] = Field(default_factory=list)


class MidiCleanupOptions(Contract):
    preserve_timing: Literal[True] = True
    remove_duplicates: bool = False
    min_duration_ticks: int = Field(default=0, ge=0, strict=True)
    quantize: bool = False
    quantize_grid_ticks: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def explicit_grid(self) -> "MidiCleanupOptions":
        if self.quantize != (self.quantize_grid_ticks is not None):
            raise ValueError(
                "quantize=true requires an explicit grid; disabled quantization has no grid"
            )
        return self


MidiCleanupOperation = Literal["remove_short_note", "remove_duplicate_note", "quantize_start"]


class MidiCleanupChange(Contract):
    operation: MidiCleanupOperation
    track_index: int = Field(ge=0)
    note_index: int = Field(ge=0)  # Position in the original imported track's notes.
    before: MidiNote
    after: MidiNote | None = None


class MidiCleanupRecord(Contract):
    algorithm_version: Literal[1] = 1
    options: MidiCleanupOptions
    changes: list[MidiCleanupChange] = Field(default_factory=list)


class ProcessedMidi(Contract):
    schema_version: Literal[1] = 1
    source: Path
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    format: Literal[0, 1] = 1
    ticks_per_beat: int = Field(gt=0)
    tracks: list[MidiTrack] = Field(default_factory=list)
    tempo_map: list[TempoEvent] = Field(default_factory=list)
    meter_map: list[MeterEvent] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    cleanup: MidiCleanupRecord | None = None


class MusicalMetadata(Contract):
    title: str = "Untitled"
    key: str | None = None


class ArrangementOptions(Contract):
    target_ppq: int | None = Field(default=None, ge=1, strict=True)
    ppq_rounding: Literal["error", "nearest"] = "error"
    note_view: Literal["imported", "active"] = "imported"
    timing_source: int | None = Field(default=None, ge=0, strict=True)


class ArrangementSource(Contract):
    input_index: int = Field(ge=0)
    note_view: Literal["imported", "cleaned"]
    midi: ProcessedMidi


class ArrangementNoteOrigin(Contract):
    note_index: int = Field(ge=0)
    input_start_tick: int = Field(ge=0)
    input_duration_ticks: int = Field(ge=0)


class InstrumentRole(Contract):
    general_midi_program: int | None = Field(default=None, ge=1, le=128, strict=True)
    plugin_hint: str | None = Field(default=None, min_length=1)
    percussion: bool = Field(default=False, strict=True)

    @field_validator("plugin_hint")
    @classmethod
    def nonblank_hint(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Plugin hint must not be blank")
        return value

    @model_validator(mode="after")
    def melodic_program_only(self) -> "InstrumentRole":
        if self.percussion and self.general_midi_program is not None:
            raise ValueError("Percussion roles cannot specify a melodic General MIDI program")
        return self


class InstrumentMappingRule(Contract):
    source_input: int = Field(ge=0, strict=True)
    source_track_position: int = Field(ge=0, strict=True)
    source_channel: int | None = Field(default=None, ge=0, le=15, strict=True)
    role: str = Field(min_length=1)


class InstrumentMappingConfig(Contract):
    schema_version: Literal[1] = 1
    roles: dict[str, InstrumentRole] = Field(default_factory=dict)
    mappings: list[InstrumentMappingRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def explicit_roles_and_selectors(self) -> "InstrumentMappingConfig":
        for name in self.roles:
            if not name.strip() or name != name.strip():
                raise ValueError("Role IDs must be nonblank without surrounding whitespace")
        selectors: set[tuple[int, int, int | None]] = set()
        for rule in self.mappings:
            if rule.role not in self.roles:
                raise ValueError(f"Unknown instrument role: {rule.role}")
            selector = (rule.source_input, rule.source_track_position, rule.source_channel)
            if selector in selectors:
                raise ValueError("Duplicate instrument mapping selector")
            selectors.add(selector)
        return self


class InstrumentMappingDocument(Contract):
    config: InstrumentMappingConfig
    source_path: Path | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class InstrumentAssignment(InstrumentRole):
    source_channel: int = Field(ge=0, le=15, strict=True)
    role: str
    rule_index: int = Field(ge=0)
    plugin_status: Literal["unverified"] = "unverified"


class InstrumentMappingTarget(Contract):
    arrangement_track_index: int = Field(ge=0)
    source_channel: int = Field(ge=0, le=15)


class InstrumentMappingMatch(InstrumentMappingTarget):
    rule_index: int = Field(ge=0)


class InstrumentMappingRecord(Contract):
    algorithm_version: Literal[1] = 1
    document: InstrumentMappingDocument
    matches: list[InstrumentMappingMatch] = Field(default_factory=list)
    unmapped: list[InstrumentMappingTarget] = Field(default_factory=list)


class ArrangementTrack(Contract):
    name: str
    source: Path
    start_tick: int = Field(default=0, ge=0)
    instrument_hint: str | None = None
    notes: list[MidiNote] = Field(default_factory=list)
    source_input: int | None = Field(default=None, ge=0)
    source_track: int | None = Field(default=None, ge=0)
    source_track_position: int | None = Field(default=None, ge=0)
    source_ticks_per_beat: int | None = Field(default=None, gt=0)
    end_tick: int = Field(default=0, ge=0)
    note_origins: list[ArrangementNoteOrigin] = Field(default_factory=list)
    instrument_roles: list[InstrumentAssignment] = Field(default_factory=list)


class Arrangement(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["faithful", "reinterpretation"] = "faithful"
    metadata: MusicalMetadata = Field(default_factory=MusicalMetadata)
    ticks_per_beat: int = Field(gt=0)
    tempo_map: list[TempoEvent] = Field(default_factory=list)
    meter_map: list[MeterEvent] = Field(default_factory=list)
    tracks: list[ArrangementTrack] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    algorithm_version: Literal[1] = 1
    sources: list[ArrangementSource] = Field(default_factory=list)
    build_options: ArrangementOptions | None = None
    instrument_mapping: InstrumentMappingRecord | None = None


class BackendCapabilities(Contract):
    backend: str
    status: Literal["available", "unavailable", "unverified"] = "unverified"
    operations: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evidence: str | None = None


class BuildResult(Contract):
    output_path: Path
    backend: str
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class ValidationReport(Contract):
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)
