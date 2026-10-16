"""Safe explicit binding YAML, preserving the exact bytes parsed."""

import hashlib
from pathlib import Path

import yaml

from suno2flp.core.build_models import TemplateBindingConfig, TemplateBindingDocument
from suno2flp.core.config import UniqueKeyLoader
from suno2flp.core.errors import ConfigurationError


def load_template_bindings(path: Path) -> TemplateBindingDocument:
    try:
        resolved = path.resolve()
        raw = resolved.read_bytes()
        config = TemplateBindingConfig.model_validate(
            yaml.load(raw.decode("utf-8-sig"), Loader=UniqueKeyLoader)
        )
        return TemplateBindingDocument(
            config=config, source_path=resolved, source_sha256=hashlib.sha256(raw).hexdigest()
        )
    except (OSError, ValueError, UnicodeError, RuntimeError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Invalid template bindings {path}: {exc}") from exc
