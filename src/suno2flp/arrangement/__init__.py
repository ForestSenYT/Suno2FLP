"""DAW-independent arrangement boundary and faithful implementation."""

from typing import Literal, Protocol

from suno2flp.arrangement.faithful import FaithfulArrangementEngine
from suno2flp.arrangement.instruments import ExplicitInstrumentMapper
from suno2flp.core.models import Arrangement, ArrangementOptions, MusicalMetadata, ProcessedMidi

__all__ = ["ArrangementEngine", "ExplicitInstrumentMapper", "FaithfulArrangementEngine"]


class ArrangementEngine(Protocol):
    def arrange(
        self,
        midi: list[ProcessedMidi],
        metadata: MusicalMetadata,
        mode: Literal["faithful", "reinterpretation"],
        *,
        options: ArrangementOptions | None = None,
    ) -> Arrangement:
        """Return a tick-based arrangement with explicit tempo and meter maps."""
        ...
