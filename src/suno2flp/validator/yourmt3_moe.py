"""Current-source, per-channel generation and independent token-decoding checks."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from suno2flp.core.audio_decode import PcmDecodeReport
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.inference_snapshot import InferenceSnapshot
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.yourmt3 import summarize_yourmt3
from suno2flp.core.yourmt3_moe import (
    YourMT3MoEBackend,
    YourMT3MoECandidate,
    YourMT3MoENative,
    check_yourmt3_moe_native,
)
from suno2flp.integrations.yourmt3_moe_backend import (
    call_yourmt3_moe_backend,
    read_yourmt3_moe_backend,
    yourmt3_moe_request,
)
from suno2flp.integrations.yourmt3_source import load_yourmt3_moe_pins
from suno2flp.integrations.yourmt3_worker import configurations_match
from suno2flp.validator.pcm_decode import verify_pcm_decode
from suno2flp.validator.transcription import check_cancel


def verify_yourmt3_moe_record(record: YourMT3MoECandidate) -> None:
    _verify_record(record)


def _verify_record(
    record: YourMT3MoECandidate, *, should_cancel: Callable[[], bool] | None = None
) -> tuple[YourMT3MoEBackend, YourMT3MoENative, PcmDecodeReport, FileIdentity]:
    check_cancel(should_cancel)
    record = YourMT3MoECandidate.model_validate(record.model_dump())
    root = guarded_path(record.root)
    if [record.raw.path, record.request.path, *[i.path for i in record.diagnostics]] != [
        root / "attempt/native.json",
        root / "attempt/request.json",
        root / "attempt/stdout.txt",
        root / "attempt/stderr.txt",
    ]:
        raise ValueError("MoE evidence paths differ from exclusive candidate layout")
    inputs = [
        record.backend,
        record.decode_report,
        record.source_audio,
        record.pcm,
        record.raw,
        record.request,
        *record.diagnostics,
    ]
    verify_inputs(inputs)
    decode = verify_pcm_decode(record.decode_report.path, should_cancel=should_cancel)
    if (record.source_audio, record.pcm, record.frames, record.sample_rate, record.channels) != (
        decode.preflight.source,
        decode.pcm,
        decode.preflight.frames,
        decode.preflight.sample_rate,
        decode.preflight.channels,
    ):
        raise ValueError("MoE source snapshot differs from independently verified PCM")
    if record.backend.path.name != "backend.json":
        raise ValueError("Expected a complete fixed MoE backend")
    backend = read_yourmt3_moe_backend(record.backend.path.parent)
    if record.raw.size_bytes > 64 * 1024**2 or record.request.size_bytes > 65536:
        raise ValueError("MoE complete raw evidence exceeds budget")
    native = YourMT3MoENative.model_validate(load_unique_json(record.raw.path.read_bytes()))
    check_yourmt3_moe_native(native, record.frames, record.sample_rate)
    pins = load_yourmt3_moe_pins()
    if not configurations_match(native.configuration, pins.configuration) or native.versions != {
        p.distribution: p.version for p in pins.wheels
    }:
        raise ValueError("MoE native runtime/configuration differs from fixed profile")
    request = yourmt3_moe_request(
        backend, record.pcm, record.frames, record.sample_rate, record.channels
    )
    if load_unique_json(record.request.path.read_bytes()) != request:
        raise ValueError("Saved MoE request differs from current source and backend")
    notes = [note for channel in native.channels for note in channel.notes]
    unresolved = [
        (window.index, channel)
        for window in native.windows
        for channel in window.unresolved_channels
    ]
    if record.summaries != summarize_yourmt3(notes, record.intervals, record.sample_rate) or (
        record.unresolved_generations != unresolved
    ):
        raise ValueError("MoE summary or unfinished-generation addresses differ from raw evidence")
    attempt = root.parent / f"yourmt3-moe-token-replay-{uuid.uuid4().hex}"
    replay_request = yourmt3_moe_request(
        backend,
        record.pcm,
        record.frames,
        record.sample_rate,
        record.channels,
        mode="decode",
        raw=record.raw.path,
    )
    replay = call_yourmt3_moe_backend(backend, attempt, replay_request)
    expected = {"channels": native.model_dump(mode="json")["channels"]}
    actual = load_unique_json(replay.path.read_bytes())
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True, allow_nan=False
    ):
        raise ValueError(
            "Independent MoE token decoding disagrees with complete13-channel evidence"
        )
    verify_inputs([*inputs, replay])
    check_cancel(should_cancel)
    return backend, native, decode, replay


def verify_yourmt3_moe(candidate_path: Path) -> YourMT3MoECandidate:
    path = guarded_path(candidate_path)
    if path.name != "yourmt3-moe.json" or path.stat().st_size > 1024**2:
        raise ValueError("Expected a bounded complete MoE candidate report")
    identity = capture_stream_input(path)
    record = YourMT3MoECandidate.model_validate(load_unique_json(path.read_bytes()))
    if record.root != path.parent:
        raise ValueError("MoE report root differs from current location")
    verify_yourmt3_moe_record(record)
    verify_inputs([identity])
    return record


@dataclass(frozen=True, slots=True)
class VerifiedMoESource:
    """Invocation-local owned proof, never accepted from serialized trust declarations."""

    _producer_json: str
    _candidate_json: str
    _native_json: str
    _backend_json: str
    _guard: InferenceSnapshot

    @property
    def producer(self) -> FileIdentity:
        return FileIdentity.model_validate_json(self._producer_json)

    @property
    def candidate(self) -> YourMT3MoECandidate:
        return YourMT3MoECandidate.model_validate_json(self._candidate_json)

    @property
    def native(self) -> YourMT3MoENative:
        return YourMT3MoENative.model_validate_json(self._native_json)

    @property
    def backend(self) -> YourMT3MoEBackend:
        return YourMT3MoEBackend.model_validate_json(self._backend_json)

    def recheck(self, *, should_cancel: Callable[[], bool] | None = None) -> None:
        self._guard.recheck(should_cancel=should_cancel)
        if read_yourmt3_moe_backend(self.backend.root).model_dump_json() != self._backend_json:
            raise ValueError("Current MoE backend/runtime/adapter recipe changed")
        check_cancel(should_cancel)


def collect_verified_moe(
    candidate_path: Path, *, should_cancel: Callable[[], bool] | None = None
) -> VerifiedMoESource:
    """Verify once, then retain exact complete source/runtime/payload witnesses."""
    check_cancel(should_cancel)
    path = guarded_path(candidate_path)
    if path.name != "yourmt3-moe.json" or path.stat().st_size > 1024**2:
        raise ValueError("Expected a bounded complete MoE candidate report")
    producer = capture_stream_input(path)
    record = YourMT3MoECandidate.model_validate(load_unique_json(path.read_bytes()))
    if record.root != path.parent:
        raise ValueError("MoE report root differs from current location")
    backend, native, decode, replay = _verify_record(record, should_cancel=should_cancel)
    packages = backend.root / "packages"
    members = capture_file_tree(packages, max_files=30000, max_bytes=4 * 1024**3)
    if {i.path.relative_to(packages).as_posix(): i.sha256 for i in members} != backend.payload:
        raise ValueError("Verified MoE payload changed while retaining evidence")
    files = [
        producer,
        record.backend,
        record.decode_report,
        record.source_audio,
        record.pcm,
        record.raw,
        record.request,
        *record.diagnostics,
        replay,
        backend.python,
        *backend.runtime,
        *backend.artifacts,
        *backend.adapters,
        decode.runtime.executable,
        decode.runtime.decoder,
        decode.runtime.verifier,
        decode.runtime.preflight,
        decode.runtime.contract,
    ]
    guard = InferenceSnapshot.capture(
        files,
        [(packages, members)],
        payload_byte_limits={packages: 4 * 1024**3},
        payload_file_limits={packages: 30000},
        should_cancel=should_cancel,
    )
    return VerifiedMoESource(
        producer.model_dump_json(),
        record.model_dump_json(),
        native.model_dump_json(),
        backend.model_dump_json(),
        guard,
    )
