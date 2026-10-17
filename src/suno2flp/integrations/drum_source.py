"""Inert fixed-wheel/source selection; no upstream setup or loader execution."""

import hashlib
import tarfile
import zipfile
from pathlib import Path

from suno2flp.core.drum_runtime import DrumPins
from suno2flp.core.offline_files import capture_stream_input, guarded_path
from suno2flp.core.offline_models import FileIdentity
from suno2flp.integrations.basic_pitch_archives import ArchiveMember, archive_members
from suno2flp.integrations.basic_pitch_backend import check_artifact
from suno2flp.integrations.beat_backend import Cancel, _copy_member, cancelled


def drum_payload(
    pins: DrumPins,
    inputs: list[FileIdentity],
    destination: Path | None = None,
    should_cancel: Cancel = None,
) -> dict[str, str]:
    if len(inputs) != 15:
        raise ValueError("Drum backend requires13 fixed wheels, source archive and MIT notice")
    result: dict[str, str] = {}
    folded: set[str] = set()

    def add(name: str, member: ArchiveMember) -> None:
        if name.casefold() in folded:
            raise ValueError("Drum dependency payload members collide")
        folded.add(name.casefold())
        result[name] = member.sha256

    for pin, identity in zip(pins.artifacts, inputs[:13], strict=True):
        cancelled(should_cancel)
        check_artifact(identity, pin)
        if identity.path.name != pin.filename:
            raise ValueError("Drum artifact name differs from fixed recipe")
        members = archive_members(
            identity.path, omitted_members=pin.omitted_members, max_member_bytes=512 * 1024**2
        )
        if any(name not in members or members[name].sha256 != h for name, h in pin.notices.items()):
            raise ValueError("Drum dependency license notice changed")
        for name, member in members.items():
            add(name, member)
        if destination is not None:
            with zipfile.ZipFile(identity.path) as archive:
                for name, member in members.items():
                    with archive.open(member.source_name) as stream:
                        _copy_member(stream, destination / name, member, should_cancel)

    source = inputs[13]
    check_artifact(source, pins.source)
    if source.path.name != pins.source.filename:
        raise ValueError("Drum source archive name differs from fixed recipe")
    members = archive_members(
        source.path, source_inventory=pins.source.source_inventory, max_member_bytes=16 * 1024**2
    )
    for name, expected in pins.source_files.items():
        if pins.source_prefix + name not in members or (
            members[pins.source_prefix + name].sha256 != expected
        ):
            raise ValueError("Selected drum source/config/checkpoint changed")
    if any(
        name not in members or members[name].sha256 != h for name, h in pins.source.notices.items()
    ):
        raise ValueError("Complete upstream Apache notice changed")
    with tarfile.open(source.path, "r:gz") as source_archive:
        for name in pins.source_files:
            cancelled(should_cancel)
            if name == "idm/utils.py":
                continue  # Audited lineage only; do not import training/decoder dependencies.
            member = members[pins.source_prefix + name]
            target = name
            if name == "LICENSE":
                target = "licenses/IDM-Apache-2.0.txt"
            elif name == pins.checkpoint_path:
                target = "models/idm.ckpt"
            elif name == pins.config_path:
                target = "models/idm-model.yaml"
            if name == "idm/synthesis_conditioning/transcription.py":
                reader = source_archive.extractfile(member.source_name)
                assert reader is not None
                with reader:
                    raw = reader.read(1024**2)
                old = b"from idm.utils import get_act_functional, get_act_module"
                new = b"from idm.audit_activations import get_act_functional, get_act_module"
                if raw.count(old) != 1:
                    raise ValueError("Fixed transcription activation import changed")
                raw = raw.replace(old, new)
                digest = hashlib.sha256(raw).hexdigest()
                if digest != pins.patched_transcription_sha256:
                    raise ValueError("Audited activation-only source patch changed")
                member = ArchiveMember(member.source_name, len(raw), digest)
                add(target, member)
                if destination is not None:
                    path = guarded_path(destination / target)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as output:
                        output.write(raw)
            else:
                add(target, member)
                if destination is not None:
                    reader = source_archive.extractfile(member.source_name)
                    assert reader is not None
                    with reader:
                        _copy_member(reader, destination / target, member, should_cancel)

    helper = capture_stream_input(Path(__file__).with_name("drum_activations.py"))
    if helper.sha256 != pins.helper_sha256:
        raise ValueError("Fixed isolated activation helper changed")
    notice = inputs[14]
    pin_notice = pins.notices[0]
    if (notice.path.name, notice.size_bytes, notice.sha256) != (
        pin_notice.filename,
        pin_notice.size_bytes,
        pin_notice.sha256,
    ):
        raise ValueError("Complete supplementary ConvNeXt MIT notice is required")
    for identity, target in ((helper, "idm/audit_activations.py"), (notice, pin_notice.target)):
        member = ArchiveMember("", identity.size_bytes, identity.sha256)
        add(target, member)
        if destination is not None:
            with identity.path.open("rb") as stream:
                _copy_member(stream, destination / target, member, should_cancel)
    return result
