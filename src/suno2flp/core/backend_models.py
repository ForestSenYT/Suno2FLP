"""Evidence contracts for the pinned, optional read-only Music2DAW integration."""

import math
from pathlib import Path, PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import ConfigDict, Field, JsonValue, model_validator
from pydantic.alias_generators import to_camel

from suno2flp.core.models import Contract, Diagnostic
from suno2flp.core.template_inventory import TemplateInventory

MUSIC2DAW_REVISION: Final = "6def9463d6fa8636bbc81010581318a39c47d3c4"
MUSIC2DAW_REPOSITORY: Final = "https://github.com/jihadkhawaja/flstudio-mcp"
SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
REQUIRED_BACKEND_FILES = frozenset(
    {
        "publish/music2daw.dll",
        "publish/music2daw.deps.json",
        "publish/music2daw.runtimeconfig.json",
        "publish/Music2Daw.Core.dll",
        "publish/Monad.FLParser.dll",
        "publish/Melanchall.DryWetMidi.dll",
        "source/LICENSE",
        "source/src/Monad.FLParser/LICENSE",
        "global.json",
        "source/src/Music2Daw.Cli/packages.lock.json",
        "source/src/Music2Daw.Core/packages.lock.json",
        "source/src/Monad.FLParser/packages.lock.json",
        "source/src/Music2Daw.Cli/obj/project.assets.json",
    }
)


class BackendProvisionRecord(Contract):
    schema_version: Literal[1]
    backend: Literal["music2daw"]
    repository: Literal["https://github.com/jihadkhawaja/flstudio-mcp"]
    revision: Literal["6def9463d6fa8636bbc81010581318a39c47d3c4"]
    license: Literal["GPL-3.0-or-later"]
    sdk_version: str = Field(pattern=r"^10\.\d+\.\d+$")
    packages: dict[str, str]
    files: dict[str, SHA256]

    @model_validator(mode="after")
    def complete_portable_inventory(self) -> "BackendProvisionRecord":
        if not REQUIRED_BACKEND_FILES.issubset(self.files):
            raise ValueError("Required executable, license, SDK or lock hashes are missing")
        if self.packages.get("Melanchall.DryWetMidi") != "8.0.3":
            raise ValueError("Expected pinned DryWetMidi 8.0.3 package")
        for name in self.files:
            path = PurePosixPath(name)
            if (
                not name
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or path.as_posix() != name
            ):
                raise ValueError("Backend inventory paths must be portable relative paths")
        return self


class FlpHeader(Contract):
    format: Literal[0] = 0
    channel_count: int = Field(ge=1, le=1000, strict=True)
    ppq: int = Field(gt=0, le=32767, strict=True)


class Music2DawSummary(Contract):
    """Validate public summary essentials, retaining all nested backend metadata."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    source_path: Path
    fl_studio_version: str = Field(min_length=1)
    tempo: float = Field(gt=0, allow_inf_nan=False)
    ppq: int = Field(gt=0, le=65535, strict=True)
    title: str
    author: str
    playlist_item_count: int = Field(ge=0, strict=True)
    channels: list[dict[str, JsonValue]]
    patterns: list[dict[str, JsonValue]]
    inserts: list[dict[str, JsonValue]]

    @model_validator(mode="after")
    def valid_ids_and_counts(self) -> "Music2DawSummary":
        def check_finite(value: JsonValue) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Backend JSON metadata must contain finite numbers")
            if isinstance(value, dict):
                for child in value.values():
                    check_finite(child)
            elif isinstance(value, list):
                for child in value:
                    check_finite(child)

        for collection in (self.channels, self.patterns, self.inserts):
            for item in collection:
                check_finite(item)
            ids = [item.get("id") for item in collection]
            if any(type(value) is not int or value < 0 for value in ids):
                raise ValueError("Backend item IDs must be nonnegative integers")
            if len(set(ids)) != len(ids):
                raise ValueError("Backend item IDs must be unique within each collection")
        for pattern in self.patterns:
            count = pattern.get("noteCount")
            if type(count) is not int or count < 0:
                raise ValueError("Backend pattern counts must be nonnegative integers")
        return self


class TemplateLocalSummary(Contract):
    scope: Literal["selected_event_families_only"] = "selected_event_families_only"
    profile_id: str
    fl_studio_version: str
    ppq: int = Field(gt=0)
    channel_count: int = Field(gt=0)
    tempo_millibpm: int | None = Field(default=None, ge=0)
    tempo_event_indices: list[int]
    pattern_note_counts: dict[int, int] | None
    pattern_event_indices: list[int]
    playlist_item_count: int | None = Field(ge=0)
    playlist_event_indices: list[int]


class BackendSummaryMismatch(Contract):
    field: str
    backend_value: JsonValue
    local_value: JsonValue
    event_indices: list[int]


class TemplateInspectionReport(Contract):
    schema_version: Literal[1] = 1
    template_path: Path
    size_bytes: int = Field(gt=0)
    template_sha256_before: SHA256
    template_sha256_after: SHA256
    backend_manifest_sha256: SHA256
    backend: BackendProvisionRecord
    runtime_version: str
    header: FlpHeader
    project: Music2DawSummary
    inventory: TemplateInventory | None = None
    local_summary: TemplateLocalSummary | None = None
    backend_summary_status: Literal["unchecked", "consistent", "inconsistent"] = "unchecked"
    backend_summary_mismatches: list[BackendSummaryMismatch] = Field(default_factory=list)
    compatibility: Literal["unverified"] = "unverified"
    diagnostics: list[Diagnostic] = Field(default_factory=list)
