"""Installed-wheel real fixed codec qualification; authored audio, no host/UI actions."""

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from threading import Event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    import suno2flp
    from suno2flp.core.errors import OfflineError
    from suno2flp.core.offline_files import capture_stream_input, verify_inputs
    from suno2flp.gui.model import JobActions, present_job
    from suno2flp.importer.encoded_audio import inspect_encoded_audio
    from suno2flp.importer.pcm_decode import decode_pcm_wave
    from suno2flp.integrations.codec_backend import provision_codec_backend
    from suno2flp.integrations.codec_process import run_bounded_process
    from suno2flp.validator.encoded_decode import verify_encoded_decode

    distribution = importlib.metadata.distribution("suno2flp")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    installed = (
        not direct.get("dir_info", {}).get("editable", False)
        and any(str(item) == "suno2flp/__init__.py" for item in distribution.files or [])
        and Path(distribution.locate_file("suno2flp/__init__.py")).resolve()
        == Path(suno2flp.__file__).resolve()
    )
    if args.require_installed and not installed:
        raise RuntimeError("Codec smoke requires a genuinely installed wheel")
    root = args.workspace.absolute()
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    backend = provision_codec_backend(
        root / "decoder", Path(sys.executable), wheelhouse=args.wheelhouse
    )
    worker = next(x.path for x in backend.adapter_files if x.path.name == "codec_worker.py")
    code = """
import sys,runpy,json
from pathlib import Path
m=runpy.run_path(sys.argv[1]); sf,np,_=m['_native'](Path(sys.argv[2])); root=Path(sys.argv[3])
a=np.random.default_rng(42).uniform(-.2,.2,(8193,2)); a[101]=.8; a[-101]=-.8
sf.write(root/'source.wav',a,44100,subtype='PCM_24')
a,r=sf.read(root/'source.wav',dtype='float64',always_2d=True)
sf.write(root/'source.flac',a,r,subtype='PCM_24'); sf.write(root/'source.mp3',a,r)
results=[]
for rate in (8000,11025,12000,16000,22050,24000,32000,44100,48000):
 for ch in (1,2):
  n=rate//4+37
  a=np.random.default_rng(rate+ch).uniform(-.2,.2,(n,ch)); a[101]=.8; a[-101]=-.8
  path=root/f'{rate}-{ch}.mp3'; sf.write(path,a,rate)
  b,r=sf.read(path,dtype='float64',always_2d=True)
  assert (len(b),r,b.shape[1])==(n,rate,ch)
  lags=range(-1024,1025)
  scores=[float(np.dot(a[max(0,-k):min(n,n-k),0],
        b[max(0,k):min(n,n+k),0])) for k in lags]
  lag=list(lags)[int(np.argmax(scores))]; assert lag==0,(rate,ch,lag)
  results.append({'name':path.name,'frames':n,'rate':rate,'channels':ch,'best_lag':lag})
print(json.dumps(results))
"""
    out, err = run_bounded_process(
        [
            str(backend.python.path),
            "-I",
            "-S",
            "-B",
            "-c",
            code,
            str(worker),
            str(backend.root / "packages"),
            str(root),
        ]
    )
    if err:
        raise RuntimeError(f"Authored codec fixtures emitted diagnostics: {err!r}")
    qualification = json.loads(out)
    for item in qualification:
        inventory = inspect_encoded_audio(root / item["name"])
        if (inventory.frames, inventory.sample_rate, inventory.channels) != (
            item["frames"],
            item["rate"],
            item["channels"],
        ):
            raise RuntimeError("Complete source timing disagrees with native presentation")
    originals = [
        capture_stream_input(root / name) for name in ("source.wav", "source.flac", "source.mp3")
    ]
    manifest = capture_stream_input(backend.root / "backend.json")
    reference = decode_pcm_wave(root / "source.wav", root / "reference")
    actions = JobActions(root / "jobs", backend.root)
    reports = []
    for codec in ("flac", "mp3"):
        created = actions.create(root / f"source.{codec}")
        result = actions.run(created.record.path, Event())
        if (
            result.job.status != "blocked"
            or present_job(result).completed != 2
            or result.job.history[-1].code != "worker_unavailable"
        ):
            raise RuntimeError(
                f"Real codec job did not qualify input/decode: {result.model_dump_json()}"
            )
        checked = actions.verify(result.record.path)
        if checked != result:
            raise RuntimeError("Independent job verification changed state")
        pcm, report, request = result.job.stages[1].outputs
        evidence = verify_encoded_decode(report.path)
        if codec == "flac" and reference.samples_sha256 != evidence.native.samples_sha256:
            raise RuntimeError("Lossless decoder differs from independently decoded integer WAV")
        reports.append(
            {
                "codec": codec,
                "record": str(result.record.path),
                "report": str(report.path),
                "request_sha256": request.sha256,
                "frames": evidence.inventory.frames,
            }
        )
        # Alter only this new synthetic candidate and all corresponding declared hashes.
        raw = bytearray(pcm.path.read_bytes())
        raw[58] ^= 1
        pcm.path.write_bytes(raw)
        data = json.loads(report.path.read_bytes())
        changed = capture_stream_input(pcm.path)
        data["pcm"] = changed.model_dump(mode="json")
        data["native"]["pcm_sha256"] = changed.sha256
        data["native"]["samples_sha256"] = hashlib.sha256(raw[58:]).hexdigest()
        report.path.write_text(json.dumps(data), encoding="utf-8")
        try:
            verify_encoded_decode(report.path)
        except OfflineError:
            pass
        else:
            raise RuntimeError("Rehashed forged PCM escaped current-source sample replay")
    for codec, transform in (("flac", lambda raw: raw + b"junk"), ("mp3", lambda raw: raw[:-1])):
        source = root / f"damaged.{codec}"
        source.write_bytes(transform((root / f"source.{codec}").read_bytes()))
        try:
            inspect_encoded_audio(source)
        except OfflineError:
            pass
        else:
            raise RuntimeError("Incomplete native-success source escaped structural checks")
    verify_inputs([manifest, *originals])
    if any(name in sys.modules for name in ("soundfile", "numpy", "cffi")):
        raise RuntimeError("Native dependencies leaked into the core application")
    result = {
        "installed": installed,
        "runtime": backend.probe.model_dump(mode="json"),
        "timing_qualification": qualification,
        "jobs": reports,
        "forged_candidates_refused": True,
        "later_workers": "blocked",
        "host_compatibility": "unverified",
        "musical_correctness": "not_assessed",
    }
    with (root / "smoke.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
