# Suno2FLP

An AI-assisted pipeline foundation from official Suno MIDI and reference
audio stems to editable FL Studio projects. Python 3.11+, Windows first.

Implemented: safe workspace creation, strict YAML configuration, recursive MIDI/WAV
discovery, basic metadata, conservative filename matching, validation, environment checks,
Phase 1 track-aware MIDI import plus opt-in deterministic note cleanup, and Phase 2
faithful arrangement construction from explicitly selected note views, with optional
explicit instrument-role annotations.
Phase 3 adds explicitly provisioned, isolated Music2DAW and hash-verified read-only
template inspection with clear prerequisite failures, plus explicit source-to-template
bindings and non-executable dry-run build plans. Read-only inventories now retain
template notes, playlist clips, automation and exact crop bits, with stronger content checks.
Exact-build [FL Studio 26.1.7.5654 read-only support](docs/FL26_READ_ONLY.md) adds
three-byte event 172 and 88-byte clips, retaining local/backend disagreements explicitly.
Source events, original ticks, tempo/meter maps and source hashes are preserved.
The [FL26 readiness batch](docs/FL26_READINESS.md) adds current-byte dependency
declarations, unresolved-semantic findings and local binding/PPQ checks. A separate
[restricted native writer](docs/FL26_WRITER.md) now implements explicit-policy note/
clip/tempo encoding, structural round-trip checks and exclusive new Windows bundles.
The current private FL26 template remains blocked by unresolved evidence. Host/playback
compatibility is unverified; synthetic byte fixtures do not establish audible results.
Transcription, reinterpretation and MCP connections remain planned. No music/model/
template or optional backend binary is bundled; project defaults remain disabled.

Phase 3's [read-only backend/template assessment](docs/FLP_BACKEND_ASSESSMENT.md)
recommends a pinned Music2DAW candidate and documents timing, licensing, runtime and
output-safety limits. The next [read-only inspection slice](docs/TEMPLATE_INSPECTION.md)
implements isolated provisioning and parsing, verified locally with synthetic inputs.
An original private FL26 template is now verified read-only. Writer adoption still
needs its dependency/semantic gates closed and independent FL Studio checks.

## Install and use

Install Python 3.11+ and uv, then from this repository:

```powershell
uv sync --locked
uv run suno2flp --help
uv run suno2flp doctor
uv run suno2flp init-project my-song
# Copy your .mid/.midi and .wav files into my-song/input.
uv run suno2flp inspect my-song/input --manifest my-song/intermediate/assets.json
uv run suno2flp import-midi my-song/input/song.mid --output my-song/intermediate/midi.json
# Optional cleanup of derived notes; thresholds/grid are explicit ticks.
uv run suno2flp clean-midi my-song/input/song.mid --remove-duplicates --min-duration-ticks 10 --quantize-grid-ticks 120 --output my-song/intermediate/cleaned.json
uv run suno2flp arrange my-song/intermediate/cleaned.json --note-view active --output my-song/intermediate/arrangement.json
# Adapt the example mapping selectors to your actual source indices/channels first.
uv run suno2flp map-instruments my-song/intermediate/arrangement.json --mapping examples/instrument_mapping.yaml --output my-song/intermediate/mapped.json
uv run suno2flp validate my-song
```

`init-project` also accepts `--directory PATH`. Existing workspace destinations and
manifest files are refused. `inspect` prints a JSON manifest by default; use
`--manifest` for an exclusively created JSON file outside the input tree.
Paths in manifests are relative to their recorded input root. No inputs are changed.
`validate` returns exit code 1 for errors; an empty workspace fails validation until
assets are supplied. Warnings do not fail validation. `doctor` reports prerequisite
presence, not verified DAW connectivity, and returns 1 only for an unsupported Python.

`import-midi` reads Type 0/1 PPQ MIDI into track-aware JSON; omit `--output` to print it.
It retains conductor/empty tracks, every decoded event in source order, original delta
and absolute ticks, paired notes, tempo/meter changes and a SHA-256 source hash.
Warnings describe ambiguous/unmatched notes; invalid tempo/meter values produce errors
and exit code 1 while retaining raw events in the result. Type 2 and SMPTE timing are
explicitly unsupported. Existing output files are refused. See [MIDI import](docs/MIDI_IMPORT.md)
for API examples, diagnostics, and timing semantics. No quantization or cleanup runs.

`clean-midi` is a separate, opt-in command. With no flags/config it changes no notes.
It can remove exact duplicates, filter notes strictly shorter than a tick threshold,
and quantize note starts to an explicit tick grid, retaining durations and all original
events/timing. Results are JSON derived-note views with a complete change audit, not
rewritten MIDI files. `--config project.yaml` uses its MIDI preferences; CLI flags
override those values. See [cleanup rules and API](docs/MIDI_CLEANUP.md).

`arrange` accepts one or more MIDI files or imported/cleaned MIDI JSON files, aligned
at beat zero. It retains all tracks, selected notes and complete input snapshots.
Mixed PPQ defaults to an exact common resolution; `--target-ppq` selects a resolution
explicitly. Inexact conversion fails unless `--allow-rounding` is selected, and every
approximation is reported. Effective tempo/meter maps must agree, including defaults;
`--timing-source N` explicitly selects a zero-based input authority when overriding
other maps. Cleaned inputs require `--note-view active`.
See [faithful arrangements](docs/ARRANGEMENT.md) for provenance, units, conflict rules
and limitations. Results are JSON.

`map-instruments` applies a validated YAML role catalog and exact source selectors to
an existing faithful arrangement. Alternatively, pass `--instruments mapping.yaml` to
`arrange`. Role annotations preserve source channels/notes/events and retain the exact
mapping document/hash. GM programs are 1-based hints; plugin labels remain unverified
text. Nothing loads plugins, sends program changes or reroutes channels. There is no
name/program-based inference. See [instrument-role mapping](docs/INSTRUMENT_MAPPING.md).
`config/instruments.yaml` is a valid catalog with empty rules and makes no assignments.

Optional FLP template inspection uses a separately provisioned pinned CLI:

```powershell
uv run suno2flp provision-music2daw .tools/music2daw-6def9463d6fa-inspect
uv run suno2flp inspect-template C:/MyTemplates/original.flp --backend-dir .tools/music2daw-6def9463d6fa-inspect --output inspection.json
```

Provisioning requires Git, SDK 10 and network access, creates a new directory only,
and records source/package/artifact evidence. Inspection needs .NET runtime 10.0,
verifies backend and template hashes, and calls only `inspect`; it never provisions
implicitly or writes FLP. JSON output requires a new path outside the backend directory.
Successful parsing leaves FL Studio/plugin compatibility and template rights unverified.
The report keeps the backend's `project` separate from a scope-limited `local_summary`.
Check `backend_summary_status`: inconsistent successful backend results are not trusted.

For exact FL Studio 26.1.7 build 5654, explicit `provision-music2daw NEW_DIRECTORY
--fl26-read-only` builds a separate source-hashed inspection adaptation from the same
pin. It fixes event-172 framing and event-233 88-byte strides; the original installation
and reports remain intact. See [adaptation limits](docs/FL26_BACKEND_ADAPTATION.md) and
[中文：创建独立参考工程](docs/FL26_REFERENCE.zh-CN.md). Selected summary agreement does not
remove unresolved note/crop/plugin/host gates or enable the upstream editor.
See [prerequisites, failure codes and tests](docs/TEMPLATE_INSPECTION.md).

For a current-file, process-free dependency/compatibility evidence report:

```powershell
uv run suno2flp assess-template inspection.json --backend-dir .tools/music2daw-6def9463d6fa-inspect --output readiness.json
```

Optionally supply `--arrangement arrangement.json --bindings bindings.yaml` together
to check local target records and exact PPQ despite backend omissions. A completed
assessment returns 0 and always reports writer blocked; missing/stale prerequisites
return 1. Local target matches do not verify audible instruments or writer support.

After adapting explicit bindings to the exact template hash and inspected IDs:

```powershell
uv run suno2flp plan-build arrangement.json --inspection inspection.json --bindings bindings.yaml --backend-dir .tools/music2daw-6def9463d6fa-inspect --output plan.json
```

`plan-build` rechecks current template/backend hashes, requires complete one-to-one
active source-channel bindings and checks exact template-PPQ conversion and the pinned
backend's conservative capability subset. No backend process or FLP write occurs.
Unsupported music produces a reviewable blocked plan (exit 1); otherwise status is
`review_required` (exit 0). Execution is always disabled and compatibility unverified.
New plans require a fresh inspection with byte-linked inventory; old summary-only
reports produce a blocked plan. Automation, crops, unbound inherited content and
ambiguous encodings block eligibility. See [inventory rules](docs/TEMPLATE_INVENTORY.md),
[planning rules](docs/BUILD_PLANNING.md) and the
[synthetic binding example](examples/template_bindings.yaml).

## Restricted FLP output

Restricted FLP output requires a new hash-pinned policy and eligible reference evidence:

```powershell
uv run suno2flp plan-flp-write arrangement.json --inspection inspection.json --bindings bindings.yaml --policy writer-policy.yaml --backend-dir .tools/music2daw-6def9463d6fa-inspect --output write-plan.json
uv run suno2flp build-flp arrangement.json --inspection inspection.json --bindings bindings.yaml --policy writer-policy.yaml --backend-dir .tools/music2daw-6def9463d6fa-inspect --output-dir output/new-build-001
uv run suno2flp verify-flp-bundle output/new-build-001 --backend-dir .tools/music2daw-6def9463d6fa-inspect
```

The [policy draft](examples/fl26_writer_policy.yaml) deliberately blocks. `build-flp`
recomputes eligibility from current documents/original MIDI, writes only a new bundle
containing FLP/provenance/verification, and never overwrites or invokes the old backend.
Unresolved notes/crops/attributes, unknown events, backend disagreement, inexact timing,
previously rounded arrangements or unverified reviews block before staging. See
[limits, policy and output protection](docs/FL26_WRITER.md).

`verify-flp-bundle` independently rechecks an existing bundle against every current
original input and the pinned backend, without writing files or launching a process.
It rejects damaged/stale/forged evidence and retains structural-only, host-unverified
status. See [saved-bundle verification and remaining host gates](docs/FL26_BUNDLE_VERIFICATION.md).

## Architecture and scope

```text
AssetImporter -> MidiProcessor -> ArrangementEngine -> FLPBuilder
                                                   -> DAWController -> QualityValidator
```

The local importer, deterministic MIDI processor, faithful arrangement engine and basic
validator are implemented. Pydantic
contracts and protocols define future stages. Official MIDI remains primary; audio is
reference material. Matching uses unique case-insensitive filenames, not instrument
recognition or MIDI track-level semantic matching. `inspect` counts MIDI tracks and
note events; `import-midi` extracts detailed tracks and timing. WAV inspection reads
headers. `validate` retains its basic metadata checks; deep MIDI import is explicit.
No deep audio analysis is performed.

## Development

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
```

Tests create small synthetic media and run offline without FL Studio, MCP, GPUs,
plugins, or agent clients. Dependency installation needs network access or a populated
uv cache. CI covers Windows/Linux and Python 3.11/3.14.

See [architecture](docs/ARCHITECTURE.md), [roadmap](docs/DEVELOPMENT_ROADMAP.md),
[dependencies](docs/DEPENDENCIES.md), [integration evidence](docs/INTEGRATIONS.md),
and [risks](docs/RISK_REGISTER.md). Keep credentials in environment variables outside
version control. Existing MIT license applies to this code; optional upstream projects
have their own licenses and are not bundled.
