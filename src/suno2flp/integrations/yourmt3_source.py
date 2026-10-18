"""Fixed local artifacts only; no model imports, network, setup or source patches."""

import zipfile
from pathlib import Path, PurePosixPath

from suno2flp.core.offline_files import load_unique_json, verify_inputs
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.yourmt3 import YourMT3Pins
from suno2flp.integrations.basic_pitch_archives import ArchiveMember, archive_members
from suno2flp.integrations.basic_pitch_backend import check_artifact
from suno2flp.integrations.beat_backend import _copy_member


def load_yourmt3_pins() -> YourMT3Pins:
    return YourMT3Pins.model_validate(
        load_unique_json(Path(__file__).with_name("yourmt3_pins.json").read_bytes())
    )


def safe_relative(name: str) -> str:
    parts = PurePosixPath(name).parts
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
    }
    if (
        not parts
        or "/".join(parts) != name
        or PurePosixPath(name).is_absolute()
        or name.endswith((".pth", ".pyc"))
        or any(
            p in (".", "..")
            or p.endswith((".", " "))
            or p.split(".")[0].upper() in reserved
            or any(c in p for c in '\\:*?"<>|')
            for p in parts
        )
    ):
        raise ValueError("Unsafe fixed artifact relative path")
    return name


def yourmt3_payload(
    pins: YourMT3Pins, inputs: list[FileIdentity], destination: Path | None = None
) -> dict[str, str]:
    if len(inputs) != len(pins.wheels) + len(pins.files):
        raise ValueError("YourMT3 requires the complete fixed artifact count")
    verify_inputs(inputs)
    result: dict[str, str] = {}
    folded: set[str] = set()

    def add(name: str, digest: str) -> None:
        safe_relative(name)
        if name.casefold() in folded:
            raise ValueError("YourMT3 payload members collide")
        folded.add(name.casefold())
        result[name] = digest

    for pin, identity in zip(pins.wheels, inputs[: len(pins.wheels)], strict=True):
        safe_relative(pin.filename)
        check_artifact(identity, pin)
        if identity.path.name != pin.filename:
            raise ValueError("YourMT3 wheel name differs from fixed artifact")
        members = archive_members(
            identity.path, omitted_members=pin.omitted_members, max_member_bytes=512 * 1024**2
        )
        if not pin.notices or any(
            n not in members or members[n].sha256 != h for n, h in pin.notices.items()
        ):
            raise ValueError("YourMT3 dependency license notice changed")
        for name, member in members.items():
            add(name, member.sha256)
        if destination is not None:
            with zipfile.ZipFile(identity.path) as archive:
                for name, member in members.items():
                    with archive.open(member.source_name) as stream:
                        _copy_member(stream, destination / name, member, None)

    for file_pin, identity in zip(pins.files, inputs[len(pins.wheels) :], strict=True):
        safe_relative(file_pin.filename)
        target = safe_relative(file_pin.target)
        if (identity.size_bytes, identity.sha256) != (file_pin.size_bytes, file_pin.sha256):
            raise ValueError("YourMT3 fixed source/checkpoint/notice artifact hash changed")
        if identity.path.parts[-len(PurePosixPath(file_pin.filename).parts) :] != (
            PurePosixPath(file_pin.filename).parts
        ):
            raise ValueError("YourMT3 source artifact path differs from fixed recipe")
        add(target, identity.sha256)
        if destination is not None:
            member = ArchiveMember(file_pin.filename, identity.size_bytes, identity.sha256)
            with identity.path.open("rb") as stream:
                _copy_member(stream, destination / target, member, None)
    verify_inputs(inputs)
    return result
