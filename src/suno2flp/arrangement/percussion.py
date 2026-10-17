"""Pure fusion of distinct inferred clocks, without invented percussion notes."""

from fractions import Fraction

from suno2flp.arrangement.inferred import build_estimated_arrangement
from suno2flp.core.drum_clock import drum_source_time
from suno2flp.core.percussion_arrangement import (
    EstimatedDrumPosition,
    PercussionArrangement,
    PercussionArrangementInputs,
    PercussionArrangementPart,
)
from suno2flp.core.performance import RationalTime


def build_percussion_arrangement(inputs: PercussionArrangementInputs) -> PercussionArrangement:
    source = PercussionArrangementInputs.model_validate(inputs.model_dump())
    pitched = build_estimated_arrangement(source.pitched)
    positions = [
        EstimatedDrumPosition(
            source_event_index=index,
            source_peak_index=peak_index,
            source_sample=RationalTime.exact(
                Fraction(peak.model_sample * source.drums.sample_rate, 44100)
            ),
            microseconds=RationalTime.exact(drum_source_time(peak.row)),
        )
        for index, (peak_index, peak) in enumerate(
            (i, p) for i, p in enumerate(source.drums.peaks) if p.domain == "source"
        )
    ]
    blockers = [b for b in pitched.blockers if b != "drums-not-transcribed"]
    blockers.extend(["drum-latency-not-calibrated", "drum-gm-routing-unavailable"])
    if not positions:
        blockers.append("empty-drum-estimates")
    return PercussionArrangement(
        inputs=source,
        parts=[
            PercussionArrangementPart(
                stem=part.stem,
                role="classified-percussion-candidate" if part.stem == "drums" else part.role,
                reference=part.reference,
                notes=part.notes,
                onsets=positions if part.stem == "drums" else [],
            )
            for part in pitched.parts
        ],
        residual=pitched.residual,
        blockers=blockers,
    )
