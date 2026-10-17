"""Fixed local rhythm inference recipe, independent of native imports."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription import ModelArtifactPin

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BeatTensor(Contract):
    shape: list[int] = Field(max_length=8)
    dtype: Literal["float32", "int64"]


class BeatPins(Contract):
    profile: Literal["beat-this-final0-cpu-windows-cp311-v1"]
    python_version: Literal["3.11.16"]
    beat_this_commit: Literal["b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c"]
    source_correspondence: dict[str, Digest]
    artifacts: list[ModelArtifactPin] = Field(min_length=19, max_length=19)
    model: ModelArtifactPin
    model_geometry: dict[str, BeatTensor] = Field(min_length=166, max_length=166)
    model_state_sha256: Literal["b7d16917d755944f81f83fbfe9e1ae098afac2106d42a3304868ec935a963ac2"]


class BeatBackend(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["beat-this-final0-cpu-windows-cp311-v1"] = (
        "beat-this-final0-cpu-windows-cp311-v1"
    )
    root: Path
    python: FileIdentity
    runtime: list[FileIdentity]
    artifacts: list[FileIdentity]
    adapters: list[FileIdentity]
    payload: dict[str, Digest]
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"


class BeatExecution(Contract):
    profile: Literal["beat-this-final0-fixed-cpu-v1"]
    intra_op_threads: Literal[8]
    inter_op_threads: Literal[1]
    deterministic_algorithms: Literal[True]
    mkldnn: Literal[False]
    cuda: None
    matmul_precision: Literal["highest"]
    model_state_sha256: Digest
    geometry: dict[str, BeatTensor]
    versions: dict[str, str]
    modules: dict[str, Path]
