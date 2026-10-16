"""Read-only inspection/planning and the future template-based FLP writer boundary."""

from pathlib import Path
from typing import Protocol

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.models import Arrangement, BackendCapabilities, BuildResult
from suno2flp.flp_builder.planning import DryRunBuildPlanner

__all__ = ["DryRunBuildPlanner", "FLPBuilder", "TemplateInspector"]


class TemplateInspector(Protocol):
    def inspect(self, template: Path) -> TemplateInspectionReport:
        """Read a template and report provenance without writing FLP or loading plugins."""
        ...


class FLPBuilder(Protocol):
    def capabilities(self) -> BackendCapabilities:
        """Declare supported operations and FL/plugin/version constraints."""
        ...

    def build(self, arrangement: Arrangement, template: Path, output: Path) -> BuildResult:
        """Write a new output exclusively; preserve template and verify output before return.

        Reject equal/resolved/linked source destinations and existing outputs. Unsupported
        operations raise IntegrationUnavailableError, never a synthetic success result.
        """
        ...
