# Dependencies

## Required foundation

Python >=3.11; uv for local dependency/environment management; Git for development.
`pyproject.toml` specifies compatible major-version ranges; `uv.lock` pins the resolved
environment. Use `uv sync --locked` to reproduce it. Wheel packaging uses Hatchling.

| Dependency | Purpose |
| --- | --- |
| Pydantic 2 | Cross-module contracts and configuration validation |
| Typer | Command-line interface |
| PyYAML 6 | Safe YAML parsing, with duplicate-key rejection |
| mido 1.3 | Read-only metadata and track-aware Standard MIDI parsing |
| pytest | Offline synthetic tests and CLI smoke tests |
| Ruff | Formatting and linting |
| mypy / types-PyYAML | Strict source type checking |

The dev group adds tooling only. No audio ML stack, MCP SDK or upstream DAW parser
is imported by the foundation. New dependencies require a concrete use and review.
Track-aware import includes a local timing compatibility check for mido 1.3.3's
unknown-metadata delta loss; see [MIDI import](MIDI_IMPORT.md). Regression fixtures
must remain when changing mido versions.

## Optional prerequisites

FFmpeg is checked but unnecessary for WAV header inspection. FL Studio is needed for
future actual project compatibility/listening tests. Claude Code and Codex are agent
clients, not required runtime dependencies. Presence of an executable is not proof of
authentication, version suitability, connectivity, or tool compatibility.

Music2DAW targets .NET 10 (SDK required for source builds; its docs describe standalone
Windows releases). PyFLP's metadata allows Python >=3.8 but current FL compatibility
needs tests. The rosasynthesiz server needs Python >=3.10, FL Studio 2025+, controller
scripts, a bridge and virtual MIDI ports (loopMIDI on Windows). demixer restricts Python
to 3.11 and has a documented runtime dependency declaration gap. Keep all optional
tools in separate environments and pin reviewed commits. See [evidence](INTEGRATIONS.md).

Phase 3 selects the isolated Music2DAW CLI source at
`6def9463d6fa8636bbc81010581318a39c47d3c4` for read-only template inspection,
outside the Python environment. Its core requests DryWetMidi 8.0.3 (MIT); the backend
and retained parser notices are GPL-3.0-or-later. The upstream tree has no SDK/NuGet
lockfile, so our provisioner records a local SDK selection, generated package locks,
resolved dependency graph and binary hashes. Nothing was added to
`pyproject.toml` or `uv.lock`. See the [full assessment](FLP_BACKEND_ASSESSMENT.md)
for pinned primary sources, licensing boundaries and the missing template gate.

The subsequent [inspection slice](TEMPLATE_INSPECTION.md) now provides explicit
`provision-music2daw` and `inspect-template`. Actual local provisioning used the same
full SHA, SDK 10.0.401 and DryWetMidi 8.0.3; inspection used runtime 10.0.12. All source,
published binaries, NuGet packages/caches and .NET CLI state stay under an ignored
installation root, with generated project locks and a hash inventory. No optional
backend enters the Python lockfile or distribution. Inspection requires only the
separate .NET runtime and verified installation; Git/SDK/network are provisioning
prerequisites, while FL Studio/plugins remain later compatibility prerequisites.

The [dry-run planning slice](BUILD_PLANNING.md) adds no dependencies. Its pure API
uses only validated snapshots and exact integer/rational arithmetic, with no file or
process access. `plan-build` additionally verifies current template and backend files
against the inspection record; this check needs no Git, .NET runtime, SDK or network.
It never invokes the backend or enables writing.

The [inventory slice](TEMPLATE_INVENTORY.md) adds only standard-library hashing,
integer and struct-based reads to the existing Python contracts. No backend patch,
helper build, parser dependency or optional binary is introduced. File planning
regenerates this local inventory without .NET; inspection still uses the same pin.
The exact [FL26 profile](FL26_READ_ONLY.md) and local/backend comparison also use only
existing contracts and standard-library arithmetic. No parser install, backend patch
or lockfile change is required; the unmodified backend remains separately provisioned.

The [FL26 readiness manifest](FL26_READINESS.md) adds no runtime or Python dependency.
It records literal plugin/sample declarations and opaque state hashes independently
of the backend's incomplete summary. Template plugin versions, formats, sample hashes,
availability and rights remain unknown; SDK/runtime/backend packages are separate
verified installation evidence. `assess-template` verifies bytes without launching
the backend or resolving/loading external dependencies.

The [restricted native writer](FL26_WRITER.md) adds no Python/runtime dependency and
does not patch or execute Music2DAW. Encoding/verifying uses original standard-library
byte operations. Publication is Windows-only because the selected no-replace directory
operation is platform-dependent; other platforms fail before staging. Backend/source
evidence stays separate, all unresolved template/dependency gates still block, and
neither private reference assets nor optional binaries enter either package format.

## Binary asset policy and Git LFS

Audio inputs, generated FLPs, temporary processing directories and secrets are ignored.
Synthetic fixtures are generated at test time. No copyrighted music is distributed.
Keep original inputs separate from disposable intermediate and output directories.

Git LFS was available during bootstrap, but no LFS initialization, filters or local
Git configuration were changed. For licensed binary templates intentionally committed
later, first inspect existing attributes and `git lfs version`; the maintainer may
then choose path-scoped LFS rules such as `templates/*.flp filter=lfs diff=lfs merge=lfs -text`.
Ignored files still require an intentional ignore-policy change or force-add. Avoid
tracking generated outputs. Binary support in `.gitattributes` alone does not enable LFS.

## Configuration and secrets

Copy `config/default.yaml` or use `init-project`; project settings live in `project.yaml`.
Relative workspace paths resolve from that file's directory. Template paths can be
absolute or relative read-only references. Environment expansion is not performed.
Unknown keys, duplicate YAML keys, unsafe paths and non-destructive=false are errors.
`config/instruments.yaml` is now a validated instrument-role catalog with empty mapping
rules. Explicitly load it using `--mapping` / `--instruments`; nothing applies it by
default. Examples and 1-based GM versus zero-based source-channel conventions are in
[INSTRUMENT_MAPPING.md](INSTRUMENT_MAPPING.md). The former placeholder drum-role
`midi_channel: 10` was replaced by `percussion: true`; destination channel fields are
rejected, and mapping never rewrites channels. No new dependency or plugin runtime
is added for this stage.
Cleanup preferences are consumed only by the explicit cleanup API/command; import,
inspection and validation do not apply them implicitly. `quantize: true` now requires
positive `quantize_grid_ticks`; configurations using the former placeholder boolean
alone must supply that grid. Backend selections still do not enable integrations.
Faithful arrangement requires no additional dependencies: PPQ and effective-map
comparison use Python integer, `math.lcm` and `fractions.Fraction` arithmetic.
Arrangement options belong to the explicit API/CLI; `arrange` does not load project
YAML or apply cleanup itself.
Store credentials only in the operator's environment/secret store; no key fields exist.
