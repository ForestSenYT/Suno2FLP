"""Predictable domain errors surfaced by the CLI."""


class Suno2FLPError(Exception):
    """Base error for expected failures."""


class ConfigurationError(Suno2FLPError):
    """Configuration could not be loaded or validated."""


class UnsafePathError(Suno2FLPError):
    """An operation risks overwriting or escaping a workspace."""


class AssetDiscoveryError(Suno2FLPError):
    """An asset directory could not be inspected."""


class MidiImportError(Suno2FLPError):
    """A MIDI source is unreadable, malformed, or uses unsupported timing."""


class MidiProcessingError(Suno2FLPError):
    """Cleanup cannot preserve provenance or the requested options are incompatible."""


class ArrangementError(Suno2FLPError):
    """A faithful arrangement cannot represent the selected sources/options safely."""


class TimingConflictError(ArrangementError):
    """Effective timing maps disagree or cannot be represented without collisions."""


class InstrumentMappingError(ArrangementError):
    """Explicit role mapping has ambiguous, unmatched, or unverifiable targets."""


class IntegrationUnavailableError(Suno2FLPError):
    """An optional backend is absent or cannot verify a capability."""


class BackendProvisionError(IntegrationUnavailableError):
    """An isolated installation could not establish the pinned backend."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


class TemplateInspectionError(IntegrationUnavailableError):
    """Read-only inspection failed a prerequisite or integrity check."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


class BuildPlanningError(Suno2FLPError):
    """Invalid bindings, snapshots or current read-only prerequisites prevent planning."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


class FlpWriteError(Suno2FLPError):
    """Restricted writing failed; existing inputs/outputs must never be overwritten."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


class OfflineError(Suno2FLPError):
    """Offline evidence, preparation or comparison cannot preserve its contract."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")
