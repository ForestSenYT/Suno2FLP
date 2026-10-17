"""Inert fixed encoder-only runtime contracts; never load native libraries here."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.drum_scoring import DRUM_CLASSES, DrumClass
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription import ModelArtifactPin, SupplementalNotice

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DrumTensor(Contract):
    shape: list[Annotated[int, Field(ge=0, strict=True)]] = Field(max_length=8)
    dtype: Literal["float32"]


class DrumPins(Contract):
    profile: Literal["idm-encoder-only-cpu-windows-cp311-v1"]
    revision: Literal["456656868538205ef756912c7cf5b0fd936de8af"]
    python_version: Literal["3.11.16"]
    artifacts: list[ModelArtifactPin] = Field(min_length=13, max_length=13)
    source: ModelArtifactPin
    notices: list[SupplementalNotice] = Field(min_length=1, max_length=1)
    source_files: dict[str, Digest] = Field(min_length=11, max_length=11)
    source_prefix: str
    checkpoint_path: Literal[
        "pretrained/idm-44-train-kits/checkpoints/val-epoch=518-global_step=0.ckpt"
    ]
    checkpoint_sha256: Literal["5856a9bee7c6d503842795756d238dc8470f6f3e010e9e4f33ede0362850cb4c"]
    config_path: Literal["pretrained/idm-44-train-kits/checkpoints/model.yaml"]
    helper_sha256: Digest
    patched_transcription_sha256: Digest
    state: dict[str, DrumTensor] = Field(min_length=330, max_length=330)
    classes: list[DrumClass] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def fixed_scope(self) -> Self:
        if (
            self.classes != list(DRUM_CLASSES)
            or sum(k.startswith("encoder.") for k in self.state) != 194
        ):
            raise ValueError(
                "Drum class order or complete encoder state differs from the fixed profile"
            )
        if len({p.distribution for p in self.artifacts}) != 13:
            raise ValueError("Duplicate drum runtime distributions")
        return self


class DrumBackend(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["idm-encoder-only-cpu-windows-cp311-v1"] = (
        "idm-encoder-only-cpu-windows-cp311-v1"
    )
    root: Path
    python: FileIdentity
    runtime: list[FileIdentity]
    artifacts: list[FileIdentity]
    adapters: list[FileIdentity]
    payload: dict[str, Digest]
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"
