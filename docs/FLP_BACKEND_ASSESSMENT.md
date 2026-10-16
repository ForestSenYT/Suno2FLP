# Phase 3: read-only FLP backend and template assessment

Audit date: 2026-10-15. **Assessment complete; writer adoption is blocked.**
This document records the original source-only assessment. The subsequent
[provisioning/inspection slice](TEMPLATE_INSPECTION.md) establishes real isolated build
and synthetic parse evidence; the uninstalled/unexecuted statements below describe
the earlier assessment, not the current CLI. Real-template/FL Studio gates remain open.
The later [binding/dry-run slice](BUILD_PLANNING.md) adds explicit target selection,
exact PPQ checks and non-executable capability plans without implementing a writer.
Recommend Music2DAW at commit `6def9463d6fa8636bbc81010581318a39c47d3c4`
as the candidate for the next controlled template inspection. This is a source-backed
engineering recommendation, not a successful backend installation or FL Studio
compatibility result. Keep `flp_backend: none`; `FLPBuilder` remains a protocol.

## Scope and evidence levels

Read pinned upstream source, licenses, package metadata and selected upstream tests;
compare them with our arrangement contracts and local prerequisites. Public-source
retrieval used Firecrawl and read-only GitHub requests. Reference source is kept only
under ignored `.tools/`; it is not incorporated into Suno2FLP. No backend was installed,
built or executed; no FLP, preset, source MIDI or audio was created or changed. No
plugin was loaded and no DAW or MCP connection was opened.

The [GitHub commit response][commit] resolves the full Music2DAW SHA, dated
2026-07-19. This pins the reviewed source, not a moving branch, latest release,
signed binary or reproducible dependency closure. Source support, installed runtime
presence, successful parsing and audible compatibility are separate evidence levels.

## Candidate decision

| Candidate | Source-backed fit | Decision |
| --- | --- | --- |
| Music2DAW, `6def9463d6fa8636bbc81010581318a39c47d3c4` | Targeted existing-template edits, JSON CLI, PPQ-based notes/playlist, retained event payloads and plugin blobs; modern 80-byte playlist path | Primary experimental candidate, with the restrictions below |
| PyFLP, `f937126b888ce94271bfea631b89166c74056530` | Python parser/save and editable models; lower-level event construction needed for new structures; PPQ changes do not rescale timings | Secondary inspection/fallback candidate, not selected for the first adapter |
| demixer, `7865ce616d4f8d3755078bbc30d4bd2da5b0a70a` | Fresh notes/stem writer with fixed PPQ 96, seconds-based rounding, merged source channels and silent note Samplers; no template-state preservation | Reject for faithful reconstruction at this pin |

The ranking is an inference from the [Music2DAW implementation][editor] and the
fresh [alternative-backend source assessment](FLP_BACKEND_ALTERNATIVES.md), which
records the other pins, licenses, runtime constraints and source links. Live FL Studio
MCP control and Ableton export are different integration surfaces, not substitutes
for this template-edit backend.

## Music2DAW capability assessment

All rows describe the pinned source, **not locally verified execution**.

| Requirement | Verified implementation and limit | Consequence for Suno2FLP |
| --- | --- | --- |
| Read-only inspection | CLI `inspect` calls `Project.Load` and builds a JSON manifest; no plugin loading or FL launch on that path. Manifest includes version/PPQ, channels, pattern note counts, playlist count and plugin payload hashes. [CLI][cli], [service][service] | Suitable next probe once provisioned; summary counts alone cannot validate every note, clip or meter event |
| Note and pattern editing | Request identifies a zero-based pattern/channel pair; editor replaces/appends 24-byte note records inside an existing recognized pattern-note event. [Schema][models], [editor][editor] | Pre-created patterns and generator channels are required; no arbitrary channel/pattern creation contract |
| Playlist | Existing recognized playlist event required; `playlist` replaces it, `playlistAdditions` appends. Layout detection includes 32/60/80-byte records; matching records supply inherited fields. Zero offset values leave template crop bytes unchanged. [Editor][editor] | Validate exact template layout, IDs and offsets; inventory and clear inherited content deliberately. Do not equate an append with faithful replacement |
| Timebase | Note/clip coordinates are signed 32-bit integers. Header PPQ is read as an unsigned 16-bit value and retained; edit request has no PPQ setter. [Schema][models], [editor][editor] | Convert into the inspected template PPQ with exact integer/rational checks; reject overflow, collapsed durations and unrepresentable ticks. The storage width is not a claim that FL accepts every PPQ |
| Tempo and meter | One `Tempo` value updates the first fine-tempo event at 0.001 BPM resolution. There are no tempo-map, meter-map or meter-setting fields. [Schema][models], [editor][editor] | Changing tempo/meter maps cannot be faithfully written. Even a constant source tempo needs a representability check; inherited automation must not override it |
| Source MIDI channels | Notes select an FL rack channel; request has no source MIDI-channel field. Exported MIDI channels/GM programs are inferred from rack IDs and names; export writes one tempo and 4/4. [Schema][models], [exporter][exporter] | FL channel IDs are not MIDI channels. Keep original source identity in the arrangement/sidecar and require explicit destination bindings. Exported MIDI is not an oracle for source-channel/map fidelity |
| Other MIDI events | No request fields for translating arbitrary CC, sustain, pitch bend, aftertouch or program-change streams. [Schema][models] | Retained JSON events do not imply equivalent FL playback; reject unsupported performance requirements before writing |
| Plugins and opaque events | Event rewriter retains unedited payloads; optional copies use existing initialization/parameter blobs. No arbitrary generator/effect creation or preset interpretation. [Editor][editor], [upstream limits][readme] | Use only approved pre-created template instruments; never treat role/plugin hints as availability or routing. Verify payload hashes separately from audible behavior |
| Output protection | Temporary write and parser re-open precede publication, but final `File.Move` uses `overwrite: true`; service checks source/output path strings, not link identity. [Editor][editor], [service][service] | Upstream is weaker than our exclusive-output contract. A future adapter must stage privately, protect links/sources, hash inputs and exclusively publish; direct delegation is insufficient |
| Validation/version scope | Upstream reports FL `25.1.2.4896`; selected synthetic tests cover edits, unknown payloads, plugin-copy pairs and FL25 playlist IDs/crop fields. [README][readme], [test source][tests] | Reported upstream coverage only. We did not run those tests or open a project in any FL build |

The CLI exposes `inspect`, `export`, `edit` and `launch`. It has no standalone
`capabilities` command; the MCP tool's capability response is descriptive source text,
not a negotiated per-template guarantee. Prefer the isolated CLI for the initial
read-only probe; do not start MCP or call export/edit/launch as part of inspection.
[CLI entry point][cli], [MCP tools][mcp].

## License and runtime findings

Music2DAW's actual root notice is **GPL-3.0-or-later**; the retained Monad.FLParser
notice also permits version 3 or later. These primary notices are the evidence, even
if a hosting service cannot classify the license. Suno2FLP's own MIT license is
unchanged; no upstream implementation or binary is bundled. Before redistribution,
review the actual combination/packaging and provide the required license/notices and
corresponding-source arrangements. An external process is useful for runtime isolation,
but does not automatically settle whether components form a combined work.
[Root notice][license], [parser notice][parser-license], [GNU aggregation guidance][gnu].

The CLI, core and parser target `net10.0`. Core references
`Melanchall.DryWetMidi` **8.0.3**, whose tagged license is MIT. The optional MCP
project additionally references `Microsoft.Extensions.Hosting` 10.0.10 and
`ModelContextProtocol` 1.4.1; MCP is unnecessary for the proposed CLI probe.
The inspected tree has no `global.json` or NuGet lockfile. Before provisioning,
record the exact SDK, resolved package graph/notices, build command and artifact hash;
the commit alone does not pin the whole build. Self-contained release bundles mentioned
upstream were not downloaded or verified and are not the recommended pin mechanism.
[CLI target][cli-project], [core dependencies][core-project],
[parser target][parser-project], [MCP metadata][mcp-project],
[DryWetMidi tagged license][drywet-license], [pinned tree][tree].

Template ownership, permission to redistribute it, FL Studio entitlement and rights
to its plugins, presets and samples are separate from the backend license. No rights
are inferred from a file being readable or from a bundled FL Studio asset. Image-Line
documents that recipients need compatible editions/plugins, matching plugin formats
and versions, and the same or a higher FL Studio version. Asset paths/availability
also need checking. [Official project-sharing guidance][sharing].

## Actual local inventory

| Check performed | Observed result | What it establishes |
| --- | --- | --- |
| Project CLI `doctor` | Python 3.11.16; Git 2.56; uv 0.12.21 | Foundation runtime remains available |
| `dotnet --list-sdks` | SDK 10.0.401 | Required .NET major SDK is present; backend restore/build is untested |
| `dotnet --list-runtimes` | .NETCore/App, ASP.NETCore/App and WindowsDesktop/App 10.0.12 | Installed .NET 10 shared runtimes, not a backend execution result |
| Application lookup on PATH | No Music2DAW or FL/FL64 application found | No executable discovered there; custom locations remain possible |
| Standard Program Files FL scan | No FL Studio candidate found | Installation/version/license remain unverified, not proven absent |
| Workspace FLP inventory, including ignored files | No `.flp`/`.FLP`; `templates/` contains only README | No project bytes available to hash or parse; no template compatibility verdict possible |
| Shipped config/example | `template_path: null`, `flp_backend: none` | No configured template/backend; defaults remain disabled |

These are bounded local checks, not a disk-wide inventory. No user template path,
ownership evidence, plugin manifest or FL version was supplied for this assessment.
Template SHA-256, header/version/PPQ, channel/pattern inventory and plugin/sample-state
compatibility are therefore **not assessed**, rather than passed with empty values.

## Blockers and required evidence before a writer

| Gate | Current blocker | Evidence needed to close it |
| --- | --- | --- |
| B1 — Licensed template | No original/authorized template | Read-only path, owner/usage and redistribution scope, SHA-256, FL save build/edition, project PPQ/meter and plugin/sample manifest; see [template checklist](../templates/README.md) |
| B2 — Pinned executable | Source verified; executable not provisioned | Isolated exact-SHA build, SDK and dependency lock/notice record, artifact hash, read-only inspect success, template hash unchanged |
| B3 — Timing/performance coverage | Map/CC writing unsupported; fine-tempo precision limited | Define and test a restricted eligible subset; reject effective tempo/meter changes, unsupported controls and inexact tick/tempo conversions. A constant 4/4 synthetic arrangement is a candidate, not yet an accepted fixture |
| B4 — Explicit template bindings | Role hints are annotations, not FL destinations | Reviewed source-input/track/channel to existing FL generator/pattern/playlist IDs; sufficient slots, mute/automation/routing inventory and no inferred substitutions. Preserve full arrangement/mapping provenance in a sidecar |
| B5 — Exclusive output safety | Upstream overwrites distinct existing outputs and does not resolve link identity | Adapter design/tests for immutable source/template hashes, private staging, safe distinct destinations, refusal of existing outputs and failure cleanup without source loss |
| B6 — Preservation and semantic verification | No local FLP parsing, rewrite or payload comparison | Separately authorized copy-only experiment: expected note/clip links and exact timing, unchanged non-target events/plugin hashes, source hashes, and deterministic result semantics. Parser success alone is insufficient |
| B7 — FL Studio validation | Host/plugins/entitlements unverified | Target build matching the template and backend-tested layout, manual open/readback/listen with licensed dependencies; no silent substitutions or missing assets |
| B8 — Distribution | Backend/template terms not cleared for a concrete package | Maintainer review of intended distribution and retained notices/source obligations; no automatic bundled backend/template |

Next authorized work should be **isolated provisioning and read-only template
inspection**, after B1's asset information is available. That stage should emit an
inspection report with unsupported requirements and hashes. Copy-only round trips,
writer implementation and DAW mutations require their own later scope; none is
enabled by this assessment. A future writer must fail closed on unmet gates rather
than flatten maps, infer instrument destinations or return a synthetic `BuildResult`.

## Verification of this repository update

Only documentation is changed in this slice; production contracts, CLI, config,
dependency lock and source assets stay untouched. Existing synthetic tests and static
checks were rerun as a regression check: Python 3.11.16 and 3.14.7 each passed 158 tests
with one existing symbolic-link test skipped for Windows account privileges. Ruff lint,
format checking and strict mypy passed. Six recorded hashes for the builder protocol,
core models, CLI, package metadata, default config and dependency lock remained unchanged;
35 local documentation links resolved and Markdown whitespace checks passed. A separate
read-only consistency check found no factual corrections in the two assessment reports.
These checks cover Suno2FLP, not an external backend. No FLP compatibility,
backend-runtime success or plugin availability is claimed. No packaging check was needed
because packaging and executable code were unchanged.

[commit]: https://api.github.com/repos/jihadkhawaja/flstudio-mcp/commits/6def9463d6fa8636bbc81010581318a39c47d3c4
[tree]: https://api.github.com/repos/jihadkhawaja/flstudio-mcp/git/trees/6def9463d6fa8636bbc81010581318a39c47d3c4?recursive=1
[readme]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/README.md
[models]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/FlpEditModels.cs
[editor]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/FlpProjectEditor.cs
[service]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/FlStudioProjectService.cs
[cli]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Cli/Program.cs
[exporter]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/MidiExporter.cs
[tests]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/tests/Music2Daw.Tests/FlpProjectEditorTests.cs
[mcp]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Mcp/FlStudioTools.cs
[cli-project]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Cli/Music2Daw.Cli.csproj
[core-project]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/Music2Daw.Core.csproj
[parser-project]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Monad.FLParser/Monad.FLParser.csproj
[mcp-project]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Mcp/Music2Daw.Mcp.csproj
[license]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/LICENSE
[parser-license]: https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Monad.FLParser/LICENSE
[drywet-license]: https://github.com/melanchall/drywetmidi/blob/v8.0.3/LICENSE
[gnu]: https://www.gnu.org/licenses/gpl-faq.html#MereAggregation
[sharing]: https://support.image-line.com/action/knowledgebase?ans=811
