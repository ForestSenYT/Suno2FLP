"""Conditional timing metrics: unmatched labels must remain visible."""

import itertools
import random
from fractions import Fraction

import pytest

from suno2flp.core.beat_scoring import ScoredBeat
from suno2flp.core.performance import RationalTime
from suno2flp.validator.beat_scoring import score_beats


def beat(id: str, time: int | Fraction, label: str = "beat") -> ScoredBeat:
    return ScoredBeat(id=id, microseconds=RationalTime.exact(Fraction(time)), label=label)


def test_wide_match_window_keeps_large_timing_errors() -> None:
    refs = [beat(str(i), i * 1000000) for i in (1, 2, 3)]
    candidates = [
        beat(str(i), i * 1000000 + error)
        for i, error in zip((1, 2, 3), (20000, 100000, 120000), strict=True)
    ]
    score = score_beats(candidates, refs)
    assert score.median_error_microseconds == RationalTime.exact(Fraction(100000))
    assert score.p95_error_microseconds == RationalTime.exact(Fraction(120000))
    assert len(score.matches) == 3


def test_maximum_cardinality_precedes_minimum_error_and_nearest_greedy() -> None:
    score = score_beats(
        [beat("c0", 400000), beat("c1", 800000)], [beat("r0", 0), beat("r1", 500000)]
    )
    assert len(score.matches) == 2
    assert {(m.candidate_id, m.reference_id) for m in score.matches} == {("c0", "r0"), ("c1", "r1")}


def test_minimum_error_is_global() -> None:
    score = score_beats(
        [beat("a", 0), beat("b", 200000), beat("c", 400000)],
        [beat("r0", 180000), beat("r1", 390000)],
    )
    assert {m.candidate_id for m in score.matches} == {"b", "c"}


def test_duplicates_are_distinct_and_labels_cannot_cross_match() -> None:
    score = score_beats([beat("a", 10), beat("b", 10), beat("db", 10, "downbeat")], [beat("r", 10)])
    assert len(score.matches) == 1
    assert len(score.unmatched_candidate_ids) == 2
    assert score.matches[0].candidate_id == "a"


@pytest.mark.parametrize(
    "reference,status", [(None, "reference_unavailable"), ([], "no_reference_beats")]
)
def test_missing_or_empty_truth_never_has_perfect_metrics(reference, status) -> None:
    score = score_beats([beat("c", 0)], reference)
    assert score.status == status
    assert score.median_error_microseconds is score.p95_error_microseconds is None
    assert score.precision is score.recall is None


def test_exact_rational_window_and_even_median() -> None:
    score = score_beats(
        [beat("a", Fraction(1, 3)), beat("b", 2000000)],
        [beat("x", Fraction(1500001, 3)), beat("y", 2000001)],
    )
    assert len(score.matches) == 2
    assert score.median_error_microseconds == RationalTime.exact(Fraction(500001, 2))
    outside = score_beats([beat("a", 0)], [beat("r", Fraction(1500001, 3))])
    assert outside.matches == [] and outside.p95_error_microseconds is None


def test_exhaustive_tiny_oracle_checks_global_count_and_error() -> None:
    rng = random.Random(17)
    for _ in range(60):
        candidates = [beat(f"c{i}", rng.randrange(12) * 100000) for i in range(4)]
        refs = [beat(f"r{i}", rng.randrange(12) * 100000) for i in range(3)]
        best = (0, Fraction(0))
        for choices in itertools.product(range(-1, len(candidates)), repeat=len(refs)):
            used = [i for i in choices if i >= 0]
            if len(used) != len(set(used)):
                continue
            errors = [
                abs(
                    Fraction(refs[r].microseconds.numerator, refs[r].microseconds.denominator)
                    - Fraction(
                        candidates[c].microseconds.numerator, candidates[c].microseconds.denominator
                    )
                )
                for r, c in enumerate(choices)
                if c >= 0
            ]
            if any(e > 500000 for e in errors):
                continue
            objective = (len(errors), -sum(errors))
            best = max(best, objective)
        score = score_beats(candidates, refs)
        errors = [
            Fraction(m.error_microseconds.numerator, m.error_microseconds.denominator)
            for m in score.matches
        ]
        assert (len(errors), -sum(errors)) == best


def test_cancel_and_duplicate_ids_fail() -> None:
    with pytest.raises(Exception, match="cancel"):
        score_beats([], [], should_cancel=lambda: True)
    with pytest.raises(ValueError, match="unique"):
        score_beats([beat("same", 0), beat("same", 1)], [])
