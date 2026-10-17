"""Inferred rhythm with complete original-source and native-execution ancestry."""

from pathlib import Path
from typing import Literal

from suno2flp.core.beat_clock import BeatAnchor
from suno2flp.core.beat_native import NativeBeatResult
from suno2flp.core.beat_runtime import BeatBackend
from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity


class BeatCandidate(Contract):
    profile: Literal["source-bound-inferred-beats-v1"] = "source-bound-inferred-beats-v1"
    root: Path
    decode_report: FileIdentity
    source_audio: FileIdentity
    pcm: FileIdentity
    decode_dependencies: list[FileIdentity]
    decoder_payload_root: Path | None
    backend_record: FileIdentity
    backend: BeatBackend
    recipe: ScoringRecipe
    native: NativeBeatResult
    native_witnesses: list[FileIdentity]
    beat_peaks: list[int]
    downbeat_peaks: list[int]
    beats: list[BeatAnchor]
    raw_downbeats: list[BeatAnchor]
    downbeat_to_beat: list[int | None]
    downbeats: list[BeatAnchor]
    signal_observations: list[
        Literal["source-silent", "downmix-cancellation", "no-beat-predictions"]
    ]
    authority: Literal["audio-inference"] = "audio-inference"
    meter_denominator: Literal["unavailable"] = "unavailable"
    drum_classes: Literal["unavailable"] = "unavailable"
    confidence_calibration: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven"] = "not_proven"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"


class BeatReplay(Contract):
    profile: Literal["source-bound-beat-native-replay-v1"] = "source-bound-beat-native-replay-v1"
    original: FileIdentity
    saved: BeatCandidate
    fresh: BeatCandidate
    comparison: Literal["complete-native-arrays-and-derived-peaks-equal"] = (
        "complete-native-arrays-and-derived-peaks-equal"
    )
    musical_correctness: Literal["not_proven"] = "not_proven"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"
