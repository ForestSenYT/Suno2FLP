"""Point-in-time output-device observations, separate from host qualification."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity

EndpointId = Annotated[str, Field(strict=True, min_length=1, max_length=4096)]
ENDPOINT_NOT_FOUND = 0x80070490


class WindowsAudioEndpoint(Contract):
    id: EndpointId
    state: int = Field(strict=True)

    @model_validator(mode="after")
    def supported_state(self) -> Self:
        if not self.id.strip() or self.state not in (1, 2, 4, 8):
            raise ValueError("Empty endpoint ID or unsupported Core Audio device state")
        return self


class WindowsAudioDefault(Contract):
    role: int = Field(strict=True, ge=0, le=2)
    hresult: int = Field(strict=True, ge=0, le=0xFFFFFFFF)
    device_id: EndpointId | None

    @model_validator(mode="after")
    def explicit_result(self) -> Self:
        if self.hresult not in (0, ENDPOINT_NOT_FOUND):
            raise ValueError("Unsupported Core Audio default HRESULT; API failure is not absence")
        if (self.hresult == 0) != (self.device_id is not None):
            raise ValueError("Default endpoint pointer and HRESULT disagree")
        return self


class WindowsAudioFacts(Contract):
    protocol: Literal["windows-render-endpoints-v1"]
    started_ns: int = Field(strict=True, ge=0)
    finished_ns: int = Field(strict=True, ge=0)
    os_version: str = Field(strict=True, min_length=1, max_length=256)
    endpoints: list[WindowsAudioEndpoint] = Field(max_length=256)
    defaults: list[WindowsAudioDefault] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def complete_snapshot(self) -> Self:
        if self.finished_ns < self.started_ns:
            raise ValueError("Observation interval is reversed")
        ids = [endpoint.id for endpoint in self.endpoints]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate endpoint IDs")
        if sorted(default.role for default in self.defaults) != [0, 1, 2]:
            raise ValueError("All three distinct default roles are required")
        active = {endpoint.id for endpoint in self.endpoints if endpoint.state == 1}
        if any(
            default.device_id is not None and default.device_id not in active
            for default in self.defaults
        ):
            raise ValueError("Default is not an active enumerated endpoint; snapshot inconsistent")
        return self


class WindowsAudioAssessment(Contract):
    status: Literal["output_absent", "default_absent", "output_detected"]
    active_count: int = Field(strict=True, ge=0, le=256)
    default_roles: list[int]
    validity: Literal["observed_interval_only"] = "observed_interval_only"
    host_compatibility: Literal["unverified"] = "unverified"
    execution_allowed: Literal[False] = False


def assess_windows_audio(facts: WindowsAudioFacts) -> WindowsAudioAssessment:
    # Revalidate mutable containers instead of trusting a previously validated object.
    snapshot = WindowsAudioFacts.model_validate(facts.model_dump(mode="json"))
    active = sum(endpoint.state == 1 for endpoint in snapshot.endpoints)
    roles = sorted(default.role for default in snapshot.defaults if default.hresult == 0)
    status: Literal["output_absent", "default_absent", "output_detected"] = (
        "output_absent" if not active else "default_absent" if not roles else "output_detected"
    )
    return WindowsAudioAssessment(status=status, active_count=active, default_roles=roles)


class WindowsAudioNative(Contract):
    protocol: Literal["windows-audio-worker-v1"]
    facts: WindowsAudioFacts
    python_version: Literal["3.11.16", "3.14.7"]
    python_abi: Literal["cp311", "cp314"]
    isolated: Literal[True]
    no_site: Literal[True]
    no_bytecode: Literal[True]
    pointer_bits: int = Field(strict=True, ge=64, le=64)
    windows_directory: Path
    libraries: list[FileIdentity] = Field(min_length=3, max_length=3)
    stream_activation_calls: int = Field(strict=True, ge=0, le=0)
    device_mutation_calls: int = Field(strict=True, ge=0, le=0)

    @field_validator("isolated", "no_site", "no_bytecode", mode="before")
    @classmethod
    def exact_worker_flag(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("Worker isolation flags must be the boolean true")
        return True

    @model_validator(mode="after")
    def fixed_discovery(self) -> Self:
        if {"cp311": "3.11.16", "cp314": "3.14.7"}[self.python_abi] != self.python_version:
            raise ValueError("Native Python ABI/version mismatch")
        if {item.path.name.lower() for item in self.libraries} != {
            "kernel32.dll",
            "ole32.dll",
            "mmdevapi.dll",
        }:
            raise ValueError("Expected exactly the three selected OS API libraries")
        system = self.windows_directory / "System32"
        if not system.is_absolute() or any(
            str(item.path.parent).casefold() != str(system).casefold() for item in self.libraries
        ):
            raise ValueError("Selected loaded API libraries must be from Windows System32")
        return self


class WindowsAudioRequest(Contract):
    protocol: Literal["windows-audio-request-v1"] = "windows-audio-request-v1"
    recipe: ScoringRecipe
    arguments: list[str] = Field(min_length=7, max_length=7)
    timeout_seconds: int = Field(strict=True, ge=15, le=15)
    max_bytes: int = Field(strict=True, ge=4 * 1024**2, le=4 * 1024**2)

    @model_validator(mode="after")
    def fixed_operation(self) -> Self:
        workers = [
            item.path for item in self.recipe.files if item.path.name == "windows_audio_worker.py"
        ]
        if len(workers) != 1 or self.arguments != [
            str(self.recipe.python_executable.path),
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            str(workers[0]),
        ]:
            raise ValueError("Request must use the declared isolated discovery worker only")
        return self


class WindowsAudioInspection(Contract):
    schema_version: Literal[1] = 1
    root: Path
    native: WindowsAudioNative
    request: FileIdentity
    request_snapshot: WindowsAudioRequest
    stdout: FileIdentity
    stderr: FileIdentity
    assessment: WindowsAudioAssessment
    validity: Literal["observed_interval_only"] = "observed_interval_only"
    host_compatibility: Literal["unverified"] = "unverified"
    execution_allowed: Literal[False] = False

    @property
    def recipe(self) -> ScoringRecipe:
        return self.request_snapshot.recipe

    @model_validator(mode="after")
    def source_bound_assessment(self) -> Self:
        if self.assessment != assess_windows_audio(self.native.facts):
            raise ValueError("Assessment differs from the complete observed facts")
        if self.native.python_version != self.recipe.python_version:
            raise ValueError("Worker did not use the declared running interpreter")
        if (
            self.stdout.path != self.root / "stdout.bin"
            or self.stderr.path != self.root / "stderr.bin"
            or self.request.path != self.root / "request.json"
        ):
            raise ValueError("Native streams must belong to this inspection directory")
        return self
