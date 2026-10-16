# Exact-build isolated Music2DAW inspection adaptation

The unchanged upstream pin `6def9463d6fa8636bbc81010581318a39c47d3c4` misreads FL26
event 172 as four bytes and recognizes playlist strides 80/60/32, not 88. This can
silently lose tempo/notes/clips or misread arrays whose sizes also divide by an old
stride. The upstream HEAD was still that pin when checked. The original installation
and its inconsistent reports remain historical evidence and are not modified.

## Explicit separate provisioning

```powershell
uv run suno2flp provision-music2daw .tools/music2daw-6def9463d6fa-fl26-inspect-v1 --fl26-read-only
uv run suno2flp inspect-template templates/user-minimal.flp --backend-dir .tools/music2daw-6def9463d6fa-fl26-inspect-v1 --output .tools/user-minimal-fl26-adapter-inspection-new.json
```

The destination and report must be new. Defaults still build the untouched upstream
CLI. The explicit option fetches the same exact revision into a separate directory,
checks the assessed parser source SHA-256
`d88ee1d4a4f82953ca3eb007ee6543cd9b456e8f5c46f74a4a2f201fcba497dc`,
and applies an original deterministic two-edit recipe before building. Wrong source
hashes, ambiguous anchors, extra tracked changes, unsafe/nested destinations and
failed prerequisites/builds produce no success manifest. Failed new directories are
retained for diagnosis and are never reused or cleaned recursively.

Only `ProjectParser.cs` in the new external checkout is modified:

- For the exact declared version `26.1.7.5654`, consume three bytes for event 172
  before classic DWORD dispatch. Truncation fails. No meaning is assigned to its value.
- For the explicit event-233 playlist case in that same build, require divisibility
  by 88 and read the full stride, including arrays also divisible by 80/60/32.
  Empty lists stay empty. Do not alter the upstream heuristic for insert-route events,
  old profiles, plugin state, note attributes or crop conversion.

The new source baseline, adapted source and modification notice are hashed alongside
every published artifact in `backend.json`. Its optional `adaptation` declaration pins
the profile, recipe fingerprint and source hashes. Verification reconstructs the
expected edited source from the retained original, checks the notice and file inventory,
and rejects mismatches even if an edited manifest rehashes altered files. This is
integrity/consistency evidence, not cryptographic build authentication or reproducible
compiler output. Legacy manifests keep their original serialization shape, preserving
older saved inspection/intent hashes and saved-bundle revalidation.

Only the original Python recipe/contracts/tests/docs are published. Fetched or generated
C# sources, source baselines, GPL notices, package caches, DLLs and manifests remain
under the ignored private installation. Upstream GPL-3.0-or-later notices remain with
the external derived backend; no third-party parser is incorporated as MIT source or
distributed in Suno2FLP archives. No Python dependency or lock change is required.

## Inspection scope and provenance

Suno2FLP refuses other builds, absent/repeated/conflicting version evidence, premature
event 172 and misaligned FL26 playlist payloads before invoking the adapted backend.
The wrapper still invokes only runtime discovery and `inspect`; it never invokes
`edit`, `export` or `launch`. The external CLI retains its upstream commands;
this option is not a sandbox and does not make its editor FL26-compatible.

The returned `project` is the actual adapted process JSON. It is not patched from the
local inventory or substituted for the old process result. Reports retain the new
backend's full adaptation/source/artifact metadata, original file hash and local raw
record evidence. Save them to new report paths and retain the original report separately.
Selected summary comparison still uses the independent local inventory and actual
process result; an unexplained mismatch remains inconsistent.

On the private original, the adapted process now agrees on **130 BPM, 96 PPQ,
five channels, four raw note records and one 88-byte playlist record**. The original
process still reports its earlier mismatches. Both installations and reports are
kept separately. This closes these demonstrated framing/count/tempo differences only.

Summary agreement does not compare every note/clip field or establish correct lane,
crop, routing, opaque attribute or plugin semantics. The upstream crop conversion and
insert-route heuristic remain unchanged; local raw float bits/extensions remain the
evidence for unresolved cases. No backend writer support is added.

Later [independent GUI field probes](FL26_FIELD_EVIDENCE.md) demonstrate integer Pattern
crop endpoints for assessed forms. They do not change this backend's float crop
conversion or expand its editor/MIDI-export guarantees. Native observations and selected
backend summaries remain separate.

Read-only native-writer planning with the new inspection remains blocked by the real
template's partial inventory, zero note lengths/flags, crops, attributes and unreviewed
instrument/prototype policy. The `writer_backend_inconsistent` diagnostic is no longer
needed for this adapted process, but other gates remain. Old plans/readiness remain
non-executable and host/playback compatibility remains unverified. No source-derived
FLP is generated. See [independent reference instructions in Chinese](FL26_REFERENCE.zh-CN.md).

## Tests

Offline tests use authored synthetic recipe text and nonexecuting build/artifact
fixtures. They test source/recipe/inventory integrity, rehashed tampering, missing
declarations, unsupported inputs before process invocation, unsafe paths and unchanged
legacy manifest serialization. Such stubs are not runtime evidence.

Opt-in genuine runtime tests use the separately built backend:

```powershell
$env:SUNO2FLP_FL26_ADAPTED_BACKEND = (Resolve-Path .tools/music2daw-6def9463d6fa-fl26-inspect-v1).Path
$env:SUNO2FLP_FL26_TEMPLATE = (Resolve-Path templates/user-minimal.flp).Path
uv run pytest tests/integration/test_fl26_backend_adapter.py
```

They check the private original read-only and originally authored 1/4/10/15-record
playlist fixtures, with event 172 before known tempo/note data. The old runtime failed
all five regressions; the adapted runtime passed them. Source bytes/mtime and backend
fingerprints are checked; no private bytes are public fixtures.

Local verification: Python 3.11 and 3.14 each passed **487 tests, 1 skipped** with
both legacy/adapted external installations enabled. Offline defaults passed **475 tests,
13 skipped** (12 external cases and the Windows symbolic-link privilege case). This
slice adds 21 unit cases and five runtime cases. Ruff/format and strict typing of 56
source modules passed; independent review found no actionable defect.

The installed wheel inspected the original with both genuine installations and kept
both full reports. It also inspected an authored synthetic writer reference with the
genuine adapted backend; its exact-source preflight was ready with empty executable
PATH, without invoking an encoder. The real original remained blocked. Two older
synthetic saved bundles still verified, confirming legacy snapshot compatibility.
Private reports/receipts stay under `.tools/`, including
`fl26-adapter-installed-verification.json`; the original SHA/size/mtime and all old
backend artifact hashes remain unchanged. No FLP derived from the private original
was created and no host acceptance was claimed.
