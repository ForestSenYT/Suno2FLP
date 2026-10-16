import logging
from pathlib import Path

from suno2flp.core.config import load_config
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.models import Arrangement, AssetManifest, Diagnostic, ValidationReport
from suno2flp.core.workspace import workspace_path
from suno2flp.importer import LocalAssetImporter


class LocalQualityValidator:
    def validate_assets(self, manifest: AssetManifest) -> ValidationReport:
        diagnostics = list(manifest.diagnostics)
        if not manifest.assets:
            diagnostics.append(
                Diagnostic(
                    code="no_assets", severity="error", message="No valid MIDI or WAV assets found"
                )
            )
        if not any(asset.kind == "midi" for asset in manifest.assets):
            diagnostics.append(
                Diagnostic(
                    code="missing_midi",
                    severity="warning",
                    message="No official MIDI supplied; transcription is not implemented",
                )
            )
        for asset in manifest.assets:
            if asset.kind == "midi" and (asset.midi is None or asset.midi.note_events == 0):
                diagnostics.append(
                    Diagnostic(
                        code="empty_midi",
                        severity="error",
                        message="MIDI has no note events",
                        path=asset.path,
                    )
                )
            if asset.kind == "wav" and (asset.audio is None or asset.audio.frames == 0):
                diagnostics.append(
                    Diagnostic(
                        code="empty_audio",
                        severity="error",
                        message="WAV has no audio frames",
                        path=asset.path,
                    )
                )
        return ValidationReport(diagnostics=diagnostics)

    def validate_arrangement(
        self,
        arrangement: Arrangement,
        expected_tracks: int | None = None,
        expected_note_events: int | None = None,
    ) -> ValidationReport:
        diagnostics = list(arrangement.diagnostics)
        if expected_tracks is not None and len(arrangement.tracks) != expected_tracks:
            diagnostics.append(
                Diagnostic(
                    code="track_count", severity="error", message="Arrangement track count differs"
                )
            )
        # A contract note represents paired note-on/off events.
        events = sum(len(track.notes) * 2 for track in arrangement.tracks)
        if expected_note_events is not None and events != expected_note_events:
            diagnostics.append(
                Diagnostic(
                    code="note_event_count",
                    severity="error",
                    message="Arrangement note event count differs",
                )
            )
        return ValidationReport(diagnostics=diagnostics)


def validate_project(project: Path) -> ValidationReport:
    report = ValidationReport()
    try:
        root = project.resolve()
        config = load_config(root / "project.yaml")
        logging.getLogger("suno2flp").setLevel(config.logging_level)
        paths = [*config.input_directories, config.intermediate_directory, config.output_directory]
        resolved = [workspace_path(root, path) for path in paths]
        for index, path in enumerate(resolved):
            if not path.is_dir():
                report.diagnostics.append(
                    Diagnostic(
                        code="missing_directory",
                        severity="error",
                        message=f"Required directory is missing: {paths[index]}",
                        path=paths[index],
                    )
                )
            for other in resolved[index + 1 :]:
                if path == other or path in other.parents or other in path.parents:
                    report.diagnostics.append(
                        Diagnostic(
                            code="overlapping_paths",
                            severity="error",
                            message="Resolved workspace directories overlap",
                        )
                    )
        template = config.template_path
        if template is not None:
            template = (root / template).resolve()
            if not template.is_file():
                report.diagnostics.append(
                    Diagnostic(
                        code="missing_template",
                        severity="error",
                        message="Configured template is missing",
                        path=template,
                    )
                )
            if any(template.is_relative_to(path) for path in resolved[-2:]):
                report.diagnostics.append(
                    Diagnostic(
                        code="unsafe_template",
                        severity="error",
                        message="Store templates outside intermediate/output directories",
                        path=template,
                    )
                )
        validator = LocalQualityValidator()
        for path in resolved[: len(config.input_directories)]:
            if path.is_dir():
                report.diagnostics.extend(
                    validator.validate_assets(LocalAssetImporter().discover(path)).diagnostics
                )
        if any(value != "none" for value in config.integrations.model_dump().values()):
            report.diagnostics.append(
                Diagnostic(
                    code="integration_unverified",
                    severity="warning",
                    message="Selected integrations are configuration only; backends unimplemented",
                )
            )
    except (Suno2FLPError, OSError, RuntimeError) as exc:
        report.diagnostics.append(
            Diagnostic(code="invalid_project", severity="error", message=str(exc))
        )
    return report
