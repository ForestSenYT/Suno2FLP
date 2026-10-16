"""Strict YAML settings. Workspace paths are relative; secrets are never settings."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, ValidationError, model_validator
from yaml.nodes import MappingNode

from suno2flp.core.errors import ConfigurationError
from suno2flp.core.models import Contract, MidiCleanupOptions


class MidiPreferences(MidiCleanupOptions):
    """Opt-in project MIDI preferences; original timing is always retained."""


class IntegrationSettings(Contract):
    flp_backend: Literal["none", "music2daw", "pyflp"] = "none"
    daw_backend: Literal["none", "rosasynthesiz"] = "none"
    transcription_backend: Literal["none", "demixer"] = "none"


class ProjectConfig(Contract):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1)
    input_directories: list[Path] = Field(default_factory=lambda: [Path("input")], min_length=1)
    intermediate_directory: Path = Path("intermediate")
    output_directory: Path = Path("output")
    template_path: Path | None = None
    midi: MidiPreferences = Field(default_factory=MidiPreferences)
    arrangement_mode: Literal["faithful", "reinterpretation"] = "faithful"
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    logging_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    non_destructive: Literal[True] = True

    @model_validator(mode="after")
    def safe_directories(self) -> "ProjectConfig":
        paths = [*self.input_directories, self.intermediate_directory, self.output_directory]
        for path in paths:
            if path.is_absolute() or path.anchor or ".." in path.parts or path == Path("."):
                raise ValueError(
                    "Workspace directories must be relative subdirectories without '..'"
                )
        for index, path in enumerate(paths):
            for other in paths[index + 1 :]:
                if path == other or path in other.parents or other in path.parents:
                    raise ValueError("Workspace directories must not overlap")
        if self.template_path and self.template_path.suffix.lower() != ".flp":
            raise ValueError("Template must be an .flp file")
        return self


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently changing a user's settings."""


def _unique_mapping(loader: UniqueKeyLoader, node: MappingNode) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ValueError("Configuration keys must be strings")
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_config(path: Path) -> ProjectConfig:
    try:
        data = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=UniqueKeyLoader)
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a YAML mapping")
        return ProjectConfig.model_validate(data)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, ValidationError) as exc:
        raise ConfigurationError(f"Invalid configuration {path}: {exc}") from exc
