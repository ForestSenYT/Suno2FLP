"""Pure estimated composition; never synthesize source MIDI, velocity or routing."""

from fractions import Fraction

from suno2flp.core.beat_clock import beat_anchor
from suno2flp.core.estimated_arrangement import (
    EstimatedArrangement,
    EstimatedArrangementInputs,
    EstimatedBoundary,
    EstimatedNotePosition,
    EstimatedPart,
    EstimatedReference,
    EstimatedRole,
)
from suno2flp.core.note_scoring import time_fraction
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime
from suno2flp.core.separation import StemName
from suno2flp.core.separation_runtime import STEMS
from suno2flp.core.stem_transcription import PITCHED_STEMS
from suno2flp.core.transcription_clock import (
    MODEL_RATE,
    owned_prediction_rows,
    resampled_frame_count,
)


def build_estimated_arrangement(inputs: EstimatedArrangementInputs) -> EstimatedArrangement:
    # Revalidation detaches mutable models/containers; caller state never becomes
    # an authority or changes an already assembled result.
    source = EstimatedArrangementInputs.model_validate(inputs.model_dump())
    if (
        tuple(s.stem for s in source.stems) != STEMS
        or tuple(p.stem for p in source.pitches) != PITCHED_STEMS
    ):
        raise ValueError("Use all canonical reference stems and pitched estimates")
    count = resampled_frame_count(source.frames, source.sample_rate)
    rows = owned_prediction_rows(count)
    references = {s.stem: s.file for s in source.stems}
    positions: dict[StemName, list[EstimatedNotePosition]] = {}

    def boundary(index: int) -> EstimatedBoundary:
        sample = count if index == len(rows) else rows[index].source_sample
        original = Fraction(sample * source.sample_rate, MODEL_RATE)
        return EstimatedBoundary(
            row_boundary=index,
            resampled_sample=sample,
            source_sample=RationalTime.exact(original),
            microseconds=RationalTime.exact(Fraction(sample * 1000000, MODEL_RATE)),
            domain="source" if original <= source.frames else "padding",
        )

    for pitch in source.pitches:
        if (
            pitch.source_audio,
            pitch.decode_report,
            pitch.frames,
            pitch.sample_rate,
            pitch.estimated_audio,
        ) != (
            source.source_audio,
            source.decode_report,
            source.frames,
            source.sample_rate,
            references[pitch.stem],
        ):
            raise ValueError("Pitched source, clock or stem differs from separation")
        offset = 0
        notes = []
        for index, note in enumerate(pitch.notes):
            if note.end_frame > len(rows) or note.bend_offset != offset:
                raise ValueError("Keep complete ordered model notes and overlapping bend addresses")
            notes.append(
                EstimatedNotePosition(
                    source_note_index=index,
                    start=boundary(note.start_frame),
                    end=boundary(note.end_frame),
                )
            )
            offset += note.bend_count
        if offset != pitch.bends.size_bytes:
            raise ValueError("Bend evidence must cover every note without truncation")
        positions[pitch.stem] = notes

    rhythm = source.rhythm
    if rhythm is not None:
        if (
            rhythm.source_audio,
            rhythm.decode_report,
            rhythm.pcm,
            rhythm.frames,
            rhythm.sample_rate,
            rhythm.channels,
        ) != (
            source.source_audio,
            source.decode_report,
            source.pcm,
            source.frames,
            source.sample_rate,
            source.channels,
        ):
            raise ValueError("Rhythm and pitched arrangement must describe the same source clock")
        for anchors in (rhythm.beats, rhythm.raw_downbeats, rhythm.downbeats):
            previous = Fraction(-1)
            for anchor in anchors:
                frame = time_fraction(anchor.analysis_frame)
                if frame <= previous or anchor != beat_anchor(
                    frame, sample_rate=source.sample_rate, source_frames=source.frames
                ):
                    raise ValueError("Keep complete strictly ordered exact rhythm anchors")
                previous = frame
        mapping = rhythm.downbeat_to_beat
        if (
            len(mapping) != len(rhythm.raw_downbeats)
            or any(
                type(i) is not int or not 0 <= i < len(rhythm.beats)
                for i in mapping
                if i is not None
            )
            or rhythm.downbeats != [rhythm.beats[i] for i in mapping if i is not None]
        ):
            raise ValueError("Keep the complete raw-to-aligned downbeat mapping")

    roles: dict[StemName, EstimatedRole] = {
        "vocals": "vocal-pitch-proxy",
        "drums": "percussion-reference",
        "bass": "bass",
        "other": "mixed-pitched",
    }

    def reference(file: FileIdentity) -> EstimatedReference:
        return EstimatedReference(file=file, end_sample=RationalTime.exact(Fraction(source.frames)))

    blockers = [
        "drums-not-transcribed",
        "tempo-meter-structure-unavailable",
        "roles-not-independent-instrument-identification",
        "model-quality-not-qualified",
        "playable-routing-unavailable",
        "host-unverified",
        "writer-blocked",
    ]
    if rhythm is None:
        blockers.append("rhythm-not-provided")
    if not any(positions.values()):
        blockers.append("empty-pitched-estimates")
    return EstimatedArrangement(
        inputs=source,
        parts=[
            EstimatedPart(
                stem=entry.stem,
                role=roles[entry.stem],
                reference=reference(entry.file),
                notes=positions.get(entry.stem, []),
            )
            for entry in source.stems
        ],
        residual=EstimatedReference(
            file=source.residual,
            encoding="stereo-little-endian-float64-raw",
            end_sample=RationalTime.exact(Fraction(source.frames)),
        ),
        blockers=blockers,
    )
