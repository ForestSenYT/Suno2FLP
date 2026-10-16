# Isolated Music2DAW provisioning and read-only template inspection

This Phase 3 slice implements explicit provisioning and `TemplateInspector` through
`Music2DawInspector`. `FLPBuilder.build` is still a protocol: there is no FLP writer,
export, launch, plugin loading or MCP connection in this integration. Project defaults
remain `flp_backend: none`; inspection does not enable a future writer.

## Provisioning

```powershell
# Requires Git, a selected stable .NET SDK 10 and access to GitHub/NuGet.
# Parent directory must already exist; destination must be completely new.
uv run suno2flp provision-music2daw .tools/music2daw-6def9463d6fa-inspect
```

The command fetches only commit `6def9463d6fa8636bbc81010581318a39c47d3c4`
from `https://github.com/jihadkhawaja/flstudio-mcp`, checks out detached HEAD and verifies
the exact revision. Git checkout hooks are disabled for these commands. It builds only
`Music2Daw.Cli`, not MCP or upstream tests, and never invokes upstream FLP operations.
Source files remain unchanged; generated locks/build outputs stay in the new directory.

Provisioning pins the selected SDK in local `global.json`, places NuGet packages,
HTTP/plugin/scratch caches and .NET CLI state inside that directory, and explicitly
uses nuget.org as the package source. Restore generates project locks; publish uses
`--no-restore`, Release, framework-dependent output and no apphost. It changes no Python
dependencies, system installation, global Git config or global environment variables.
The OS, Git/.NET installation and user process environment are not a hermetic sandbox.

`backend.json` is written only after all commands, source checks and hashing succeed.
It contains schema version, exact source URL/SHA, GPL notice, SDK version, resolved
NuGet package versions and SHA-256 for every published artifact plus SDK config,
upstream license notices, generated locks and the CLI's resolved assets graph.
Identity fields and the assets-graph hash are mandatory when loading the record;
missing provenance is rejected rather than reconstructed from defaults.
`provision.log` retains command outputs. This is a local integrity/provenance record,
not a signed attestation or proof that redistributing the backend is approved.

Existing destinations are refused even if incomplete. On failure, retain the partial
directory/log for diagnosis and select a fresh directory after correcting the cause;
there is no destructive cleanup, automatic repair or silent reuse. Do not edit the
published files or manifest to bypass a failure. Actual artifact hashes are specific
to the build and path; identical binaries across different installations are not promised.

Music2DAW and its included parser are GPL-3.0-or-later; resolved DryWetMidi 8.0.3
declares MIT in its NuGet metadata. Upstream source/notices are retained in the private
installation, excluded from Suno2FLP distributions. See the pinned primary sources and
distribution limits in [the assessment](FLP_BACKEND_ASSESSMENT.md). Provisioning does
not license templates, plugins, presets or samples.

## Inspect a user-selected template

```powershell
uv run suno2flp inspect-template C:/MyTemplates/original.flp --backend-dir .tools/music2daw-6def9463d6fa-inspect
uv run suno2flp inspect-template C:/MyTemplates/original.flp --backend-dir .tools/music2daw-6def9463d6fa-inspect --output inspection.json --timeout 30
```

Inspection never provisions automatically and performs no network requests itself.
It needs a valid explicit backend directory and a discoverable .NETCore runtime 10.0;
SDK, Git, FL Studio, virtual MIDI, plugins and MCP are not prerequisites for parsing.
The runtime rolls forward only within the installed runtime's patch family.

Before process execution, verify the provisioning schema/pin, mandatory file hashes,
all published files and confined relative inventory paths. A missing, modified or
additional published artifact fails. Read the selected `.flp`, hash its bytes and
validate a project FLhd header against this pin's parser limits: format 0, header
length 6, 1..1000 channels, positive PPQ <=32767. These are backend constraints, not
a complete FLP validation or a claim that every value works in FL Studio.

The only backend call is an argument list equivalent to
`dotnet <backend>/publish/music2daw.dll inspect <resolved-template>`, without a shell.
It runs with a bounded timeout and the isolated environment. Recheck the original
template and backend hashes after the inspection process, including process failure
or timeout. Detected changes fail; this detects changes rather than preventing a
misbehaving process or hostile concurrent filesystem edits. Use trusted local inputs
and a trusted local provisioning record. Large files/process output are not resource-isolated.

Require successful process exit and valid JSON summary fields, consistent source path,
PPQ and channel count, nonnegative unique item IDs and pattern counts. Retain all nested
channel/plugin/sample/pattern/mixer metadata; nonfinite numbers anywhere in that metadata
are rejected rather than silently serialized as null. Plugin-state text hints can contain private
preset information; review reports before sharing them.

Reports include template path/size and before/after SHA-256, parsed header, full local
backend provisioning record and its byte hash, runtime selection and typed backend
summary, plus the [byte-linked template inventory](TEMPLATE_INVENTORY.md).
Exact [FL26 read-only support](FL26_READ_ONLY.md) retains the old backend summary
alongside a local selected-family summary and comparison status/mismatches. An
inconsistent report remains read-only evidence, not a compatibility success.
Inventory framing is checked before any backend process; raw records and float bits
are retained alongside offsets/hashes. Partial or unsupported inventories remain
explicitly limited and block dry-run v2; no unknown content is inferred safe.
`project` field names follow the typed Python contract; nested backend
metadata retains its original keys and values. No timestamps or random choices are added.
`compatibility` is always `unverified`: warnings explicitly distinguish parser results
from FL Studio opening/playback, plugin availability, template rights and writer eligibility.
Backend-inferred MIDI channel/program values are metadata guesses, not original source
channel evidence or routing instructions. Summary counts do not prove full map or clip fidelity.

Omitting `--output` prints JSON. An output must be a new `.json` with an existing
parent, outside the backend directory and distinct from the input. Existing files and
symlink destinations are refused before inspection. Reports are exclusively created.
Colons outside the drive component are refused, including NTFS alternate data streams
such as `original.flp:inspection.json`, which are not separate report files.
Failed prerequisites/inspection create no report. Inputs and existing outputs are never
intentionally changed. There is no FLP output destination argument.

## Predictable failures

CLI failures return 1 with a stable bracketed domain code; invalid CLI options return 2.

| Code | Meaning / correction |
| --- | --- |
| `destination_exists` | Choose a new isolated provisioning directory |
| `prerequisite_missing`, `sdk_unavailable` | Provisioning needs Git and a selected stable SDK 10 |
| `source_fetch_failed`, `source_checkout_failed`, `source_revision_mismatch`, `source_changed` | Fetch/check out the exact pin; inspect the preserved log/source state |
| `restore_failed`, `build_failed`, `provision_failed` | Installation incomplete; review the log and prerequisites, then use a fresh directory |
| `backend_manifest_invalid` | Missing/invalid local provisioning record, wrong pin or unsafe/incomplete inventory |
| `backend_integrity_failed` | Missing, added or modified artifact, escaping inventory path, or changed record |
| `template_unreadable`, `template_invalid` | Missing/unreadable source or unsupported FLP header; do not fabricate success |
| `template_inventory_invalid` | Malformed chunk/event framing; fails before any backend process or output |
| `dotnet_missing`, `dotnet_runtime_missing` | Inspection needs .NETCore 10.0 runtime on the selected PATH |
| `backend_timeout`, `backend_process_failed` | Backend did not complete/read the project successfully |
| `backend_output_invalid` | Invalid/inconsistent backend summary; retain the original source |
| `template_changed` | Input hash changed or input disappeared during inspection; investigate before retrying |

Path/output errors use the existing `UnsafePathError` and do not create a report.
No failure grants permission to use edit/export/launch or to discard unsupported events.

## Tests and actual local evidence

Default tests use original tiny temporary template inputs and process doubles only
at the external Git/.NET boundary; they run offline without the optional backend.
They exercise exact source selection, isolated build/cache arguments, generated evidence,
partial provisioning, integrity mismatches, prerequisite failures, header limits,
timeouts/process errors, invalid JSON and source changes on both success/failure paths.
CLI tests cover explicit use, new-report safety and absent output on failures.
Review regression cases cover omitted provenance/assets hashes, nonfinite nested JSON
and alternate-stream report paths, with stream writes blocked by a test double even
during the failing-test stage.

Opt-in tests execute the real pinned CLI on an independently authored one-channel,
one-note temporary input and malformed input. Tests create their own original input
fixtures only; neither integration nor backend writes an FLP output or edits an existing
project. To enable these checks explicitly:

```powershell
$env:SUNO2FLP_MUSIC2DAW_DIR = (Resolve-Path .tools/music2daw-6def9463d6fa-inspect).Path
uv run pytest tests/integration/test_template_external.py
```

Without that variable they skip with a clear prerequisite message; an explicitly
configured but broken installation fails rather than skipping.

Local provisioning on Windows completed at the full reviewed SHA with SDK 10.0.401,
runtime 10.0.12 and DryWetMidi 8.0.3. The source checkout had no tracked changes.
The real CLI's synthetic inspection and parse-failure tests passed with unchanged
input hashes. No user-owned real template was supplied; its rights, dependency manifest,
FL Studio version and audible compatibility remain unverified. Timing-map writing,
source-channel bindings, copied-output safety and FL Studio open/listen gates from
the assessment remain prerequisites for any future writer.

The subsequent [binding and dry-run slice](BUILD_PLANNING.md) now implements explicit
source-to-template bindings and exact PPQ/capability planning from this evidence.
Planning rechecks current files without invoking the backend. It preserves the
inspection's unverified status; deeper structure, safe copied output and FL Studio
open/listen checks remain writer prerequisites.

Inspection-slice verification (2026-10-15): Python 3.11.16 and 3.14.7 each passed **199 tests,
1 skipped** with the real backend explicitly enabled. Default offline execution passed
**197 tests, 3 skipped**: two opt-in backend tests plus the existing Windows symbolic-link
privilege skip. Ruff lint/format and strict mypy (30 source files) passed. Both package
formats built; the installed wheel exercised real synthetic parsing, JSON reports,
existing-file/alternate-stream refusal, missing prerequisites and malformed-input failures.
Original fixture and backend-record hashes stayed unchanged. Archive inspection found
no isolated source/cache/environment, FLP input or backend binary in the distribution.
All three concrete review findings were reproduced with failing regression tests and
fixed before the complete test runs. No real-template or audible result is claimed.

The verified local installation is `.tools/music2daw-6def9463d6fa-inspect` (ignored).
Its build-specific evidence fingerprints are:

| Artifact | SHA-256 |
| --- | --- |
| `backend.json` | `a79d1356d6330eb568bf8c69e6942935b6d578df5a7b1dc4e992694f9c42b7aa` |
| `publish/music2daw.dll` | `377727cd35ded8257b536a9cb6c76d88fa0619849557cece58bce9827cac543d` |

These identify this local build only; use each installation's own complete verified
record rather than copying these hashes into another machine's manifest.
