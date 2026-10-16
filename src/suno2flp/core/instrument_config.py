"""Strict role-mapping YAML loader with a hash of the exact bytes parsed."""

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from suno2flp.core.config import UniqueKeyLoader
from suno2flp.core.errors import ConfigurationError
from suno2flp.core.models import InstrumentMappingConfig, InstrumentMappingDocument


def load_instrument_mapping(path: Path) -> InstrumentMappingDocument:
    try:
        resolved = path.resolve()
        raw = resolved.read_bytes()
        data = yaml.load(raw.decode("utf-8-sig"), Loader=UniqueKeyLoader)
        if not isinstance(data, dict):
            raise ValueError("Instrument mapping must be a YAML mapping")
        return InstrumentMappingDocument(
            config=InstrumentMappingConfig.model_validate(data),
            source_path=resolved,
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )
    except (
        OSError,
        UnicodeError,
        RuntimeError,
        yaml.YAMLError,
        ValueError,
        ValidationError,
    ) as exc:
        raise ConfigurationError(f"Invalid instrument mapping {path}: {exc}") from exc
