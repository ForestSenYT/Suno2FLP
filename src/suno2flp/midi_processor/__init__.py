"""MIDI processing boundary and opt-in deterministic note cleanup."""

from pathlib import Path
from typing import Protocol

from suno2flp.core.config import MidiPreferences
from suno2flp.core.models import Asset, ProcessedMidi
from suno2flp.midi_processor.cleanup import DeterministicMidiProcessor

__all__ = ["DeterministicMidiProcessor", "MidiProcessor"]


class MidiProcessor(Protocol):
    def process(
        self, asset: Asset, source_root: Path, preferences: MidiPreferences
    ) -> ProcessedMidi:
        """Retain source timing and provenance; report every transformation and warning."""
        ...
