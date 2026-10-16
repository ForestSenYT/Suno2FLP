"""Metadata inspection only; no audio inference or MIDI editing."""

import os
import stat
import wave
from collections import defaultdict
from pathlib import Path
from typing import Literal

import mido

from suno2flp.core.errors import AssetDiscoveryError
from suno2flp.core.models import (
    Asset,
    AssetManifest,
    AssetMatch,
    AudioMetadata,
    Diagnostic,
    MidiMetadata,
)


class LocalAssetImporter:
    def discover(self, directory: Path) -> AssetManifest:
        root = directory.resolve()
        if not root.is_dir():
            raise AssetDiscoveryError(f"Input directory does not exist: {directory}")
        manifest = AssetManifest(root=root)

        def walk_error(error: OSError) -> None:
            manifest.diagnostics.append(
                Diagnostic(code="unreadable_directory", severity="error", message=str(error))
            )

        for current, directories, files in os.walk(root, followlinks=False, onerror=walk_error):
            # Junctions and symbolic links are skipped even when they point inside the root.
            for name in sorted(directories.copy()):
                child = Path(current) / name
                # lstat works for Windows junctions on Python 3.11 too.
                try:
                    attributes = getattr(child.lstat(), "st_file_attributes", 0)
                except OSError as exc:
                    directories.remove(name)
                    walk_error(exc)
                    continue
                if child.is_symlink() or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    directories.remove(name)
                    manifest.diagnostics.append(
                        Diagnostic(
                            code="linked_path",
                            severity="warning",
                            message="Linked directory skipped",
                            path=child.relative_to(root),
                        )
                    )
            directories.sort()
            for name in sorted(files):
                path = Path(current) / name
                relative = path.relative_to(root)
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    manifest.diagnostics.append(
                        Diagnostic(
                            code="linked_path",
                            severity="warning",
                            message="Linked file skipped",
                            path=relative,
                        )
                    )
                    continue
                suffix = path.suffix.lower()
                if suffix not in {".mid", ".midi", ".wav"}:
                    manifest.diagnostics.append(
                        Diagnostic(
                            code="unsupported_file",
                            severity="warning",
                            message="Supported formats: .mid, .midi, .wav",
                            path=relative,
                        )
                    )
                    continue
                kind: Literal["midi", "wav"] = "wav" if suffix == ".wav" else "midi"
                try:
                    asset = Asset(path=relative, kind=kind, size_bytes=path.stat().st_size)
                    if kind == "wav":
                        with wave.open(str(path), "rb") as audio:
                            asset.audio = AudioMetadata(
                                channels=audio.getnchannels(),
                                sample_rate=audio.getframerate(),
                                frames=audio.getnframes(),
                                sample_width_bytes=audio.getsampwidth(),
                                duration_seconds=audio.getnframes() / audio.getframerate(),
                            )
                    else:
                        midi = mido.MidiFile(path)
                        asset.midi = MidiMetadata(
                            format=midi.type,
                            tracks=len(midi.tracks),
                            ticks_per_beat=midi.ticks_per_beat,
                            note_events=sum(
                                msg.type in {"note_on", "note_off"}
                                for track in midi.tracks
                                for msg in track
                            ),
                        )
                    manifest.assets.append(asset)
                except (
                    OSError,
                    EOFError,
                    ValueError,
                    TypeError,
                    KeyError,
                    IndexError,
                    wave.Error,
                    ZeroDivisionError,
                ) as exc:
                    manifest.diagnostics.append(
                        Diagnostic(
                            code="invalid_asset",
                            severity="error",
                            message=f"Cannot inspect media: {exc}",
                            path=relative,
                        )
                    )
        manifest.assets.sort(key=lambda asset: asset.path.as_posix())
        self._match(manifest)
        return manifest

    @staticmethod
    def _match(manifest: AssetManifest) -> None:
        groups: dict[str, list[Asset]] = defaultdict(list)
        for asset in manifest.assets:
            groups[asset.path.stem.casefold()].append(asset)
        for name in sorted(groups):
            group = groups[name]
            midi = [asset for asset in group if asset.kind == "midi"]
            audio = [asset for asset in group if asset.kind == "wav"]
            if len(midi) == len(audio) == 1:
                manifest.matches.append(
                    AssetMatch(midi_path=midi[0].path, audio_path=audio[0].path)
                )
            elif midi and audio:
                manifest.diagnostics.append(
                    Diagnostic(
                        code="ambiguous_match",
                        severity="warning",
                        message=f"Multiple candidates for '{name}'; no match inferred",
                    )
                )
            else:
                manifest.diagnostics.append(
                    Diagnostic(
                        code="unmatched_asset",
                        severity="warning",
                        message=f"No filename counterpart for '{name}'",
                    )
                )
