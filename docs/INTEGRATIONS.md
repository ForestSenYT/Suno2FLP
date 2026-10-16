# Integration evidence and strategy

Bootstrap source-audit date: 2026-10-15. README, package/build metadata, license notices and selected
source files were read from GitHub. Commit IDs below were obtained from the GitHub
API. This original audit was source verification, not a runtime test: none of these projects was
installed, executed, copied, or modified. No FL Studio interoperability was tested.

Phase 3 refresh: [backend/template assessment](FLP_BACKEND_ASSESSMENT.md) and
[alternative-backend evidence](FLP_BACKEND_ALTERNATIVES.md) re-read the relevant pinned
sources and record actual local prerequisites. Music2DAW is recommended only as a
candidate for isolated template inspection; no backend is enabled. Public reference
source snapshots in ignored `.tools/` are not incorporated into this package.

Subsequent Phase 3 runtime evidence: [isolated provisioning and read-only inspection](TEMPLATE_INSPECTION.md)
are implemented. The exact Music2DAW SHA was fetched/built locally with SDK 10.0.401,
runtime 10.0.12 and resolved DryWetMidi 8.0.3. Generated locks, retained notices and
every published file are hashed in a local `backend.json`. Real synthetic parsing and
explicit parse-failure checks passed without changing inputs. This supersedes the
bootstrap's uninstalled status only for this CLI inspection surface; there is still no
FLP writer, MCP connection, real-template result or FL Studio compatibility claim.

The next [dry-run planning slice](BUILD_PLANNING.md) consumes that inspection evidence
without invoking Music2DAW. Explicit source-to-template bindings pin both the template
hash and full backend revision. A versioned, source-assessed capability profile checks
exact PPQ conversion and known backend limits; every plan remains non-executable and
compatibility stays unverified. This is not an implemented writer adapter.

[Template inventories](TEMPLATE_INVENTORY.md) now supplement the same unmodified
backend's summary with an original local reader. Known note/clip/automation/crop
layouts retain raw evidence; unknown/ambiguous layouts block v2 planning. The
inventory is cross-checked against current bytes and summary counts. No upstream
parser code, plugin state or backend binary is copied into the Python package.

The [FL26 read-only profile](FL26_READ_ONLY.md) verified an original private input at
26.1.7.5654. The fixed backend exits successfully but misses notes/clips and returns
its default tempo. Inspection retains that result explicitly as inconsistent with
local bytes. This does not upgrade the backend, establish FL26 writer support or
claim complete project semantics/playback.

The [FL26 readiness batch](FL26_READINESS.md) records 24 byte-linked declarations
from that private original, including literal sample references and separate rack/
mixer context hints. Local binding/PPQ previews retain original backend omissions
and full source snapshots. Assessment verifies current files without a process;
dependency availability, semantic edit policy and host validation remain unresolved.
The [proposed writer](FL26_WRITER_DESIGN.md) is documentation only and does not alter
the backend, dependency locks or disabled execution policy.

The subsequent [native writer implementation](FL26_WRITER.md) is a separate explicit
policy/intent workflow, not adoption of the old backend's editor. It preserves the
backend installation, blocks its unresolved FL26 disagreement and validates original
synthetic output bytes independently. The private real template remains ineligible;
no host open/playback claim or automated instrument substitution is introduced.

The [isolated FL26 inspection adaptation](FL26_BACKEND_ADAPTATION.md) now builds a
separate private derived installation from that same pin, using an original recipe
guarded by exact upstream/source/recipe hashes. Only exact-build event-172 framing and
explicit event-233 stride selection change. Genuine process output now matches the
private source's selected tempo/count facts. The unmodified backend/report is retained;
no third-party source/binary is distributed, and upstream editor/MCP/host compatibility
is not upgraded. Unknown crops/attributes/routing and native-writer gates remain open.

The later [discovery-only MCP boundary](MCP_DISCOVERY.md) implements original pinned
protocol negotiation, bounded stdio and fresh paginated inventory with synthetic peers.
The later [isolated adoption audit](FLSTUDIO_MCP_AUDIT.zh-CN.md) genuinely initialized
two fixed servers and verified 5/67-tool inventories, fresh lists, ping and clean exit.
No tool execution surface is exposed; actual host/bridge adoption remains unverified.

## suno-to-ableton

Revision: `b74e345c0ea166a5be09b5293c5aad4d6cd676e4`.
[Repository](https://github.com/steven-ahfu/suno-to-ableton),
[README](https://github.com/steven-ahfu/suno-to-ableton/blob/b74e345c0ea166a5be09b5293c5aad4d6cd676e4/README.md).

Documents stem/MIDI cleanup and Ableton session export. Python >=3.11; package metadata
includes librosa/soundfile and optional Demucs. Source confirms MIDI cleanup functions
and a template-based XML ALS exporter, not an FLP writer. Reusable design ideas include
source alignment, cleanup diagnostics and template selection. Keep any future invocation
in an isolated process and translate its outputs into our contracts. ALS templates and
Ableton version conversions do not establish FL compatibility. No direct dependency.

Evidence: [metadata](https://github.com/steven-ahfu/suno-to-ableton/blob/b74e345c0ea166a5be09b5293c5aad4d6cd676e4/pyproject.toml),
[cleanup](https://github.com/steven-ahfu/suno-to-ableton/blob/b74e345c0ea166a5be09b5293c5aad4d6cd676e4/suno_to_ableton/midi_cleanup.py),
[ALS exporter](https://github.com/steven-ahfu/suno-to-ableton/blob/b74e345c0ea166a5be09b5293c5aad4d6cd676e4/suno_to_ableton/features/export_als.py).
[License](https://github.com/steven-ahfu/suno-to-ableton/blob/b74e345c0ea166a5be09b5293c5aad4d6cd676e4/LICENSE): AGPL-3.0;
do not copy upstream code into this MIT package without a distribution/license review.

## Music2DAW — jihadkhawaja/flstudio-mcp

Revision: `6def9463d6fa8636bbc81010581318a39c47d3c4`.
[Repository](https://github.com/jihadkhawaja/flstudio-mcp),
[README](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/README.md).

C#/.NET 10 toolkit for FLP inspection, targeted edits into a new copy, arranged MIDI
export, manifests/plugin-state extraction and project launching. MCP uses local stdio.
Documented tools include capability inspection, inspect, edit, export and launch.
Source confirms net10.0 and MCP server registration. This is a candidate template-edit
backend behind FLPBuilder, via a separately provisioned CLI/MCP process and JSON requests.
Its tick positions use project PPQ and IDs are zero-based. A playlist request can replace
the whole arrangement; supported event edits do not prove arbitrary project synthesis
or live playback control. Verify exact template/plugin/version behavior before adopting.

The Phase 3 source assessment also confirms important gaps: the edit request has no
tempo/meter maps, PPQ setter or source MIDI-channel field, and edits need existing
template structures. MIDI export infers channels/programs and writes 4/4, so it cannot
validate original MIDI-channel/map fidelity. Despite its distinct-source-path check,
the editor can overwrite an existing destination (`File.Move(..., overwrite: true)`);
it does not meet Suno2FLP's exclusive-output/link-identity contract by itself.
See the [capability table and adoption blockers](FLP_BACKEND_ASSESSMENT.md).

Evidence: [build target](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Mcp/Music2Daw.Mcp.csproj),
[server registration](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Mcp/Program.cs).
[License notice](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/LICENSE)
explicitly says GPL-3.0-or-later and includes modified Monad.FLParser under its retained
GPL notice. GitHub's API returned NOASSERTION; the actual license file is decisive evidence.
Do not bundle its parser or binaries as MIT code; review redistribution before adoption.

## rosasynthesiz/flstudio-mcp

Revision: `e6eff37e45a076098ed81ee4e50fb7bf08aef11a`.
[Repository](https://github.com/rosasynthesiz/flstudio-mcp),
[README](https://github.com/rosasynthesiz/flstudio-mcp/blob/e6eff37e45a076098ed81ee4e50fb7bf08aef11a/README.md).

Python >=3.10/FastMCP server with live mixer, transport, parameter and note tools.
Source registers tool groups; metadata defines server/daemon entry points. Requires
FL Studio 2025+, controller scripts and virtual MIDI ports; Windows uses loopMIDI.
Notes require an armed piano-roll bridge. Documented API limitations leave plugin/audio
loading and rendering manual. Candidate DAWController adapter: separately install,
handshake, discover tools, then validate readback per operation. Published tool counts
are not our capability contract. Custom plugin calibration, focus/bridge setup, and
host version remain compatibility risks. No bridge or GUI automation was installed.

Evidence: [metadata](https://github.com/rosasynthesiz/flstudio-mcp/blob/e6eff37e45a076098ed81ee4e50fb7bf08aef11a/pyproject.toml),
[server](https://github.com/rosasynthesiz/flstudio-mcp/blob/e6eff37e45a076098ed81ee4e50fb7bf08aef11a/src/fl_studio_mcp/server.py).
[License](https://github.com/rosasynthesiz/flstudio-mcp/blob/e6eff37e45a076098ed81ee4e50fb7bf08aef11a/LICENSE): MIT;
retain required copyright/license notices if code is later redistributed.

## PyFLP

Revision: `f937126b888ce94271bfea631b89166c74056530`.
[Repository](https://github.com/demberto/PyFLP),
[README](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/README.md).

Unofficial Python FLP parser with save support and project/track/pattern models.
Metadata requires Python >=3.8; source implements parse/save and header/version checks.
Candidate for separately isolated template inspection/round-trip experiments behind
FLPBuilder. Native plugin coverage is limited; opaque plugin states and new FL versions
need explicit fixture tests. Upstream recommends backups and opening modified projects
in FL Studio. Parsing/saving alone does not establish faithful audible reconstruction
or a supported blank-project generator. No compatibility claim for our environment.

Evidence: [metadata](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyproject.toml),
[parse/save implementation](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/__init__.py).
[License](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/LICENSE): GPL-3.0;
source headers specify version 3 or later. Preserve notices and review combined-work
distribution before any adoption; no code imported or copied here.

## demixer

Revision: `7865ce616d4f8d3755078bbc30d4bd2da5b0a70a`.
[Repository](https://github.com/revoydotdev/demixer),
[README](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/README.md).

Experimental separation/transcription/analysis and DAW handoff pipeline, including an
FLP writer module. Requires Python >=3.11,<3.12 and FFmpeg; optional engines use isolated
workers and model checkpoints. Metadata has empty runtime dependencies, a documented
fresh-install blocker. Source confirms child-process orchestration; successful pipeline
completion need not mean every optional output exists. Reusable ideas are bundle
provenance, worker isolation and explicit artifact checks. Consider only an opt-in
transcription process for missing MIDI, after provisioning/accuracy tests. No models
downloaded; its FLP writer is not an established Suno2FLP backend.

Evidence: [metadata](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/pyproject.toml),
[worker orchestration](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/src/demixer/app/pipeline_runner.py),
[FLP module location](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/src/demixer/core/project/flstudio.py).
[License](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/LICENSE): AGPL-3.0-or-later;
model/data/library terms are separate. No bundling or copied implementation.

## Adoption gates

Isolation manages dependencies; it does not automatically settle license obligations.
Before adoption, verify the pinned component's terms and intended distribution,
install separately, run read-only synthetic/template tests, negotiate capabilities,
and record runtime evidence. Only then enable a narrowly scoped adapter. No integration
is enabled by default or auto-installed. Agent clients use the CLI today; there is no
Suno2FLP MCP server or agent-specific production skill yet.
