from pathlib import Path
from typing import Protocol

from suno2flp.core.models import AssetManifest


class AssetImporter(Protocol):
    def discover(self, directory: Path) -> AssetManifest:
        """Discover and validate supported media, then record conservative matches."""
        ...
