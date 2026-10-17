"""Opt-in original full upstream graph, separate from the bounded overlap-add worker."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def main() -> None:
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    root = request_path.parent
    spec = importlib.util.spec_from_file_location(
        "_full_graph_helper", Path(request["owned"]) / "spleeter_worker.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    np, session, waveform, outputs, proof = helper.native(Path(request["packages"]), root)
    source = np.fromfile(request["model_input"], dtype="<f4").reshape(request["frames"], 2)
    try:
        result = helper.predict(np, session, waveform, outputs, source)
        hashes = {}
        for stem in ("vocals", "drums", "bass", "other"):
            path = root / f"{stem}.f32"
            with path.open("xb") as stream:
                result[stem].astype("<f4", copy=False).tofile(stream)
            with path.open("rb") as stream:
                hashes[stem] = hashlib.file_digest(stream, "sha256").hexdigest()
    finally:
        session.close()
    with (root / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(
            dict(
                execution={
                    k: v
                    for k, v in proof.items()
                    if k not in ("profile", "fixtures", "repeatability_scope")
                },
                output_sha256=hashes,
            ),
            stream,
            indent=2,
        )


if __name__ == "__main__":
    main()
