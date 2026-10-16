"""Original deterministic recipe; upstream source and binaries remain external."""

import hashlib
from typing import Final

UPSTREAM_PARSER_SHA256 = "d88ee1d4a4f82953ca3eb007ee6543cd9b456e8f5c46f74a4a2f201fcba497dc"
PARSER_PATH = "source/src/Monad.FLParser/ProjectParser.cs"
BASELINE_PATH = "source/.suno2flp-upstream-ProjectParser.cs"
NOTICE_PATH = "source/SUNO2FLP-FL26-INSPECTION.txt"
PROFILE: Final = "fl26-26.1.7.5654-inspect-v1"
NOTICE = (
    "Suno2FLP local inspection adaptation: " + PROFILE + "\n"
    "Modified only ProjectParser.cs: exact-build event 172 framing and event 233 stride.\n"
    "Original upstream source is retained beside this notice; see backend.json hashes.\n"
    "This derived external backend retains its upstream GPL-3.0-or-later notices.\n"
    "Inspection only through Suno2FLP; no editor/export/launch compatibility is claimed.\n"
).encode()

EDITS = (
    (
        b"if (eventId < Enums.Event.Word)",
        b'if ((int)eventId == 172 && _project.VersionString == "26.1.7.5654")\n'
        b"            {\n"
        b"                if (reader.ReadBytes(3).Length != 3)\n"
        b'                    throw new FlParseException("Truncated FL26 event 172", startPos);\n'
        b"                return;\n"
        b"            }\n\n"
        b"            if (eventId < Enums.Event.Word)",
    ),
    (
        b"var playlistRecordSize = GetPlaylistRecordSize(dataLen);",
        b'var playlistRecordSize = _project.VersionString == "26.1.7.5654"\n'
        b"                        ? (dataLen % 88 == 0 ? 88\n"
        b'                            : throw new FlParseException("Invalid FL26 playlist size",'
        b" dataStart))\n"
        b"                        : GetPlaylistRecordSize(dataLen);",
    ),
)
RECIPE_SHA256 = hashlib.sha256(b"\0".join(part for edit in EDITS for part in edit)).hexdigest()


def adapt_parser_bytes(raw: bytes) -> bytes:
    if hashlib.sha256(raw).hexdigest() != UPSTREAM_PARSER_SHA256:
        raise ValueError("Upstream parser source differs from the exact assessed SHA-256")
    for before, after in EDITS:
        if raw.count(before) != 1:
            raise ValueError("Adaptation anchor is missing or ambiguous")
        raw = raw.replace(before, after, 1)
    return raw
