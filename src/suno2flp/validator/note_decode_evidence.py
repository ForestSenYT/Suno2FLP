"""Retain all verified decoder witnesses through matching and publication."""

from pathlib import Path

from pydantic import BaseModel

from suno2flp.core.audio_decode import PcmDecodeReport
from suno2flp.core.encoded_decode import EncodedDecodeReport, EncodedDecodeRequest
from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import NoteScoreReport
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.importer.note_annotations import bounded_snapshot


def _identities(value: object) -> list[FileIdentity]:
    if isinstance(value, FileIdentity):
        return [value.model_copy(deep=True)]
    if isinstance(value, BaseModel):
        return [identity for child in value.__dict__.values() for identity in _identities(child)]
    if isinstance(value, dict):
        return [identity for child in value.values() for identity in _identities(child)]
    if isinstance(value, (list, tuple)):
        return [identity for child in value for identity in _identities(child)]
    return []


def decode_dependencies(
    report: PcmDecodeReport | EncodedDecodeReport,
) -> tuple[list[FileIdentity], Path | None]:
    identities = _identities(report)
    payload_root = None
    if isinstance(report, EncodedDecodeReport):
        identity, raw = bounded_snapshot(report.request.path, 1024**2)
        if identity != report.request:
            raise OfflineError("note_score_decode_changed", "Decoder attempt changed")
        request = EncodedDecodeRequest.model_validate(load_unique_json(raw))
        identities.extend(_identities(request))
        payload_root = guarded_path(report.backend.root / "packages")
        for name, expected in sorted(report.backend.payload.items()):
            identity = capture_stream_input(payload_root / name)
            if identity.sha256 != expected:
                raise OfflineError("note_score_decode_changed", "Decoder payload changed")
            identities.append(identity)
    unique: dict[Path, FileIdentity] = {}
    for identity in identities:
        if identity.path in unique and unique[identity.path] != identity:
            raise OfflineError(
                "note_score_decode_changed", "Inconsistent decoder witness identities"
            )
        unique[identity.path] = identity
    return [unique[path] for path in sorted(unique)], payload_root


def verify_note_witnesses(report: NoteScoreReport) -> None:
    verify_inputs(report.witnesses())
    verify_decoder_payload(report.decode_dependencies, report.decoder_payload_root)


def verify_decoder_payload(dependencies: list[FileIdentity], root: Path | None) -> None:
    """Both scoring and transcription retain exact verified decoder payload membership."""
    if root is not None:
        guarded_path(root)
        expected = {
            identity.path for identity in dependencies if identity.path.is_relative_to(root)
        }
        actual = set()
        for path in root.rglob("*"):
            path = guarded_path(path)
            if path.is_file():
                actual.add(path)
        if actual != expected:
            raise OfflineError("note_score_decode_changed", "Decoder payload inventory changed")
