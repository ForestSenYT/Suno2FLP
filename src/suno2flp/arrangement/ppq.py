"""Integer tick conversion with explicit precision policy and source diagnostics."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from suno2flp.core.errors import ArrangementError
from suno2flp.core.models import Diagnostic


@dataclass
class TickConverter:
    target_ppq: int
    source_ppq: int
    rounding: Literal["error", "nearest"]
    diagnostics: list[Diagnostic]
    source_path: Path
    source_input: int

    def convert(
        self, tick: int, label: str, track_index: int | None = None, event_index: int | None = None
    ) -> int:
        numerator = tick * self.target_ppq
        quotient, remainder = divmod(numerator, self.source_ppq)
        if not remainder:
            return quotient
        if self.rounding == "error":
            raise ArrangementError(
                f"PPQ {self.source_ppq}->{self.target_ppq} cannot represent {label} "
                f"at tick {tick} exactly; choose higher PPQ or explicitly allow rounding"
            )
        rounded = (2 * numerator + self.source_ppq) // (2 * self.source_ppq)
        self.diagnostics.append(
            Diagnostic(
                code="ppq_rounded",
                severity="warning",
                message=f"{label}: source tick {tick} -> {rounded} at PPQ {self.target_ppq}",
                path=self.source_path,
                source_input=self.source_input,
                track_index=track_index,
                event_index=event_index,
            )
        )
        return rounded
