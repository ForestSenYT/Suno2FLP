"""Original exact-clock fixtures and an independent exhaustive matching oracle."""

from fractions import Fraction
from random import Random

import pytest
from pydantic import ValidationError

from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import ScoredNote
from suno2flp.core.performance import RationalTime
from suno2flp.validator.note_matching import score_notes


def note(identifier, onset=0, offset=1_000_000, pitch=60):
    return ScoredNote(
        id=identifier,
        pitch=pitch,
        onset_microseconds=RationalTime.exact(Fraction(onset)),
        offset_microseconds=RationalTime.exact(Fraction(offset)),
    )


def test_augmenting_path_beats_greedy_without_mutating_original_order():
    reference = [note("r1", 60_000, 1_060_000), note("r0")]
    candidate = [note("a", 45_000, 1_045_000), note("b")]
    before = [n.model_dump() for n in reference + candidate]
    score = score_notes(candidate, reference)
    assert score.status == "measured"
    assert score.true_positives == 2
    assert [(m.reference_id, m.candidate_id) for m in score.matches] == [("r0", "b"), ("r1", "a")]
    assert score.f1.numerator == score.f1.denominator == 1
    assert [n.model_dump() for n in reference + candidate] == before
    assert score == score_notes(list(reversed(candidate)), list(reversed(reference)))


@pytest.mark.parametrize("extra, matched", [(Fraction(0), 1), (Fraction(1, 44100), 0)])
def test_inclusive_onset_boundary_without_rounding(extra, matched):
    result = score_notes([note("c", 50_000 + extra)], [note("r")])
    assert result.true_positives == matched


@pytest.mark.parametrize(
    "ref_end,cand_end,matched",
    [
        (250_000, 300_000, 1),
        (250_000, 300_001, 0),
        (1_000_000, 1_200_000, 1),
        (1_000_000, 1_200_001, 0),
        (Fraction(1_000_000, 3), 400_000, 1),
        (Fraction(1_000_000, 3), 400_000 + Fraction(1, 44100), 0),
    ],
)
def test_offset_tolerance_uses_exact_reference_duration(ref_end, cand_end, matched):
    assert (
        score_notes([note("c", offset=cand_end)], [note("r", offset=ref_end)]).true_positives
        == matched
    )


def test_duplicates_are_independent_and_wrong_pitch_never_matches():
    result = score_notes([note("c1"), note("c2"), note("c3", pitch=61)], [note("r")])
    assert result.true_positives == 1
    assert result.precision.numerator == 1 and result.precision.denominator == 3
    assert result.recall.numerator == result.recall.denominator == 1
    assert result.f1.numerator == 1 and result.f1.denominator == 2
    assert result.unmatched_candidate_ids == ["c2", "c3"]
    assert score_notes([note("c")], [note("r1"), note("r2")]).true_positives == 1


def test_empty_candidate_is_zero_but_empty_or_missing_reference_is_unscored():
    zero = score_notes([], [note("r")])
    assert zero.status == "measured" and zero.f1.numerator == zero.precision.numerator == 0
    assert zero.unmatched_reference_ids == ["r"]
    for reference, status in [(None, "reference_unavailable"), ([], "no_reference_notes")]:
        score = score_notes([note("c")], reference)
        assert score.status == status
        assert score.f1 is score.precision is score.recall is None
        assert score.unmatched_candidate_ids == ["c"]


def test_long_augmenting_chain_is_iterative():
    count = 1200
    refs = [note(f"r{i:04}", i * 60_000, i * 60_000 + 1_000_000) for i in range(count)]
    candidates = [note("z")] + [
        note(f"a{i:04}", i * 60_000 - 15_000, i * 60_000 + 985_000) for i in range(1, count)
    ]
    assert score_notes(candidates, refs).true_positives == count


def brute_count(refs, candidates):
    def visit(i, used):
        if i == len(refs):
            return 0
        best = visit(i + 1, used)
        for j, candidate in enumerate(candidates):
            if j not in used and refs[i].pitch == candidate.pitch:
                r = refs[i]
                onset_error = abs(
                    r.onset_microseconds.numerator - candidate.onset_microseconds.numerator
                )
                offset_error = abs(
                    r.offset_microseconds.numerator - candidate.offset_microseconds.numerator
                )
                duration = r.offset_microseconds.numerator - r.onset_microseconds.numerator
                if onset_error <= 50_000 and offset_error <= max(50_000, Fraction(duration, 5)):
                    best = max(best, 1 + visit(i + 1, used | {j}))
        return best

    return visit(0, set())


def test_seeded_small_inputs_agree_with_independent_exhaustive_oracle():
    rng = Random(20261016)
    for _ in range(150):
        refs = [
            note(f"r{i}", t := rng.randrange(6) * 30_000, t + 200_000, rng.choice([60, 61]))
            for i in range(rng.randrange(1, 7))
        ]
        candidates = [
            note(f"c{i}", t := rng.randrange(6) * 30_000, t + 200_000, rng.choice([60, 61]))
            for i in range(rng.randrange(7))
        ]
        assert score_notes(candidates, refs).true_positives == brute_count(refs, candidates)


def test_dense_input_and_cancellation_fail_completely():
    with pytest.raises(OfflineError, match="edge"):
        score_notes([note(f"c{i}") for i in range(450)], [note(f"r{i}") for i in range(450)])
    with pytest.raises(OfflineError, match="cancel"):
        score_notes([note("c")], [note("r")], should_cancel=lambda: True)


def test_duplicate_ids_oversized_notes_and_invalid_positions_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        score_notes([note("c"), note("c")], [note("r")])
    with pytest.raises(OfflineError, match="note"):
        score_notes([note(f"n{i}") for i in range(10001)], None)
    for kwargs in [
        {"offset": 0},
        {"pitch": True},
        {"pitch": 128},
        {"onset": -1},
        {"onset": 2**129},
    ]:
        with pytest.raises((ValidationError, ValueError)):
            note("bad", **kwargs)
