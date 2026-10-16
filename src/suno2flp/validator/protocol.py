from typing import Protocol

from suno2flp.core.models import Arrangement, AssetManifest, ValidationReport


class QualityValidator(Protocol):
    def validate_assets(self, manifest: AssetManifest) -> ValidationReport: ...

    def validate_arrangement(
        self,
        arrangement: Arrangement,
        expected_tracks: int | None = None,
        expected_note_events: int | None = None,
    ) -> ValidationReport: ...
