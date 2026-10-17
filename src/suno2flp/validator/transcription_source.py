"""Fresh source clock and decoder provenance for native inference consumers."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from suno2flp.core.audio_input import AudioPreflightReport
from suno2flp.core.encoded_audio import EncodedAudioInventory
from suno2flp.core.offline_files import load_unique_json, verify_inputs
from suno2flp.core.offline_models import FileIdentity
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.validator.encoded_decode import verify_encoded_decode
from suno2flp.validator.note_decode_evidence import decode_dependencies, verify_decoder_payload
from suno2flp.validator.pcm_decode import verify_pcm_decode


@dataclass(frozen=True)
class TranscriptionSource:
    decode_report: FileIdentity
    source: FileIdentity
    pcm: FileIdentity
    frames: int
    sample_rate: int
    channels: int
    dependencies: list[FileIdentity]
    decoder_payload_root: Path | None


def verified_transcription_source(
    decode_report: Path, *, should_cancel: Callable[[], bool] | None = None
) -> TranscriptionSource:
    identity, raw = bounded_snapshot(decode_report, 1024**2)
    declared = load_unique_json(raw)
    profile = declared.get("profile") if isinstance(declared, dict) else None
    source: AudioPreflightReport | EncodedAudioInventory
    if profile == "integer-pcm-to-float64-wave-v1":
        pcm = verify_pcm_decode(decode_report, should_cancel=should_cancel)
        source = pcm.preflight
        decoded = pcm.pcm
        dependencies, payload_root = decode_dependencies(pcm)
    elif profile == "qualified-compressed-to-float64-v1":
        encoded = verify_encoded_decode(decode_report, should_cancel=should_cancel)
        source = encoded.inventory
        decoded = encoded.pcm
        dependencies, payload_root = decode_dependencies(encoded)
    else:
        raise ValueError("Transcription requires current independently verified decoded audio")
    dependencies = [identity, *dependencies]
    verify_inputs(dependencies)
    verify_decoder_payload(dependencies, payload_root)
    return TranscriptionSource(
        identity,
        source.source,
        decoded,
        source.frames,
        source.sample_rate,
        source.channels,
        dependencies,
        payload_root,
    )
