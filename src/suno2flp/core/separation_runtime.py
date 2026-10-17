"""Fixed separation runtime evidence; native execution is not music qualification."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription import ModelArtifactPin, SupplementalNotice

STEMS = ("vocals", "drums", "bass", "other")
PROBE_FRAMES = {"silence": 1025, "impulses": 12347, "stereo-pattern": 44117}
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SeparationArtifactPin(ModelArtifactPin):
    size_bytes: int = Field(gt=0, le=512 * 1024**2, strict=True)


class CheckpointMemberPin(Contract):
    source_name: str
    target: str
    size_bytes: int = Field(gt=0, le=256 * 1024**2, strict=True)
    sha256: Digest


class SpleeterPins(Contract):
    profile: Literal["spleeter4-local-graph-windows-cp311-v1"]
    python_version: Literal["3.11.16"]
    spleeter_commit: Literal["c8854001ac8acad34a9bc2bd15f28475541828b1"]
    checkpoint_prefix: Literal["model/model"]
    source_correspondence: dict[str, Digest]
    artifacts: list[SeparationArtifactPin] = Field(min_length=50, max_length=50)
    notices: list[SupplementalNotice] = Field(min_length=4, max_length=4)
    model: SeparationArtifactPin
    model_members: list[CheckpointMemberPin] = Field(min_length=5, max_length=5)


class SpleeterBackend(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["spleeter4-local-graph-windows-cp311-v1"] = (
        "spleeter4-local-graph-windows-cp311-v1"
    )
    root: Path
    python: FileIdentity
    runtime: list[FileIdentity]
    artifacts: list[FileIdentity]
    adapters: list[FileIdentity]
    payload: dict[str, Digest]
    curated_install: Literal["local-graph-no-cli-no-mwf-no-cloud"] = (
        "local-graph-no-cli-no-mwf-no-cloud"
    )
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False


class SeparationFixtureResult(Contract):
    fixture: Literal["silence", "impulses", "stereo-pattern"]
    frames: int = Field(gt=0, strict=True)
    channels: Literal[2] = 2
    sample_rate: Literal[44100] = 44100
    hashes: dict[str, list[Digest]]

    @model_validator(mode="after")
    def complete_repeat(self) -> Self:
        if self.frames != PROBE_FRAMES[self.fixture] or set(self.hashes) != set(STEMS):
            raise ValueError("Native probe must cover the complete fixed stereo fixture")
        if any(len(pair) != 2 or pair[0] != pair[1] for pair in self.hashes.values()):
            raise ValueError("Both native runs must have identical complete stem bytes")
        return self


class SpleeterExecution(Contract):
    graph_profile: Literal["spleeter4-cpu-no-remapping-v1"]
    device_types: list[Literal["CPU"]] = Field(min_length=1, max_length=1)
    intra_op_threads: Literal[8]
    inter_op_threads: Literal[1]
    versions: dict[str, str]
    modules: dict[str, Path]
    restored_variables: dict[str, list[int]] = Field(min_length=1, max_length=1024)
    restored_values_sha256: Digest
    tfio_loaded: Literal[False]
    ambient_plugins_enabled: Literal[False]


class NativeSeparationProbe(SpleeterExecution):
    profile: Literal["spleeter4-native-probe-v1"]
    fixtures: list[SeparationFixtureResult] = Field(min_length=3, max_length=3)
    repeatability_scope: Literal["observed-two-runs-per-fixture"]

    @model_validator(mode="after")
    def complete_fixtures(self) -> Self:
        if {f.fixture for f in self.fixtures} != set(PROBE_FRAMES):
            raise ValueError("Native probe needs every fixed fixture exactly once")
        return self


class SeparationSignalEvidence(Contract):
    fixture: str
    source: FileIdentity
    outputs: list[FileIdentity] = Field(min_length=8, max_length=8)
    residual: FileIdentity
    residual_peak: float = Field(ge=0, allow_inf_nan=False)
    conservation_error: float = Field(ge=0, allow_inf_nan=False)
    impulse_peak_frames: list[int] | None = None


class SpleeterProbe(Contract):
    profile: Literal["spleeter4-runtime-evidence-v1"] = "spleeter4-runtime-evidence-v1"
    backend_record: FileIdentity
    backend: SpleeterBackend
    native: NativeSeparationProbe
    evidence: list[SeparationSignalEvidence] = Field(min_length=3, max_length=3)
    request: FileIdentity
    result: FileIdentity
    stdout: FileIdentity
    stderr: FileIdentity
    model_qualification: Literal["not_assessed"] = "not_assessed"
    music_quality: Literal["not_assessed"] = "not_assessed"
    whole_song_support: Literal["not_implemented"] = "not_implemented"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
