# Dependencies

The [audio FLP candidate](AUDIO_FLP_CANDIDATE.zh-CN.md) adds no package, downloaded
model, sample bank or upstream implementation. Its percussion DSP is original;
generation captures current source, Python and math/struct/wave file identities
(built-in Windows math is bound to the current Python DLL). Exact proprietary
reference FLPs, plugin states and FL Studio remain private, separately installed
inputs, absent from Git and distributions. GPL/AGPL alternatives were researched,
not adopted: see [path audit](research/2026-10-17-flp-backend-paths.zh-CN.md).

The [Spleeter local graph runtime](SPLEETER_RUNTIME.zh-CN.md) pins50 official wheels,
the official v1.4.0 4stems archive and four supplemental notices in
`integrations/spleeter_pins.json`. Spleeter2.4.2 maps to
`c8854001ac8acad34a9bc2bd15f28475541828b1`; model archive SHA256 is
`3adb4a50ad4eb18c7c4d65fcf4cf2367a07d48408a5eb7d03cd20067429dfaa8`.
The explicit Windows CPU recipe uses TensorFlow/Intel2.12.1, NumPy1.24.3,
SciPy1.15.3 and pandas1.5.3 in a separate payload, without core lock changes.
The [complete source-bound separation route](SEPARATION.zh-CN.md) reuses this same
payload; its parent validation/overlap-add/residual checks use only the standard library.
Observed Windows child memory metrics add no package dependency. No model or native
runtime enters the application wheel/sdist or the default offline test environment.
Default Spleeter's mandatory TFIO0.32.0 has no Windows wheel. This local-graph recipe
retains TensorFlow's metadata-compatible0.31.0 but disables its native plugin; it does
not claim the upstream Spleeter closure or TFIO compatibility. CLI/FFmpeg/MWF/cloud
paths remain unsupported. Pandas is a real top-level import even for inference.

All50 wheel notices/native terms and four exact official source licenses are retained.
Supplemental notices cover FlatBuffers25.12.19, TensorFlow2.12.1's Windows meta-package,
Estimator2.12.0 and TensorBoard data-server0.7.2 (its own data-server tag). Spleeter code
and model MIT attribution follows the authors' published JOSS statement, with the
README/question ambiguity preserved. Main distribution labels do not replace bundled
GCC/LLVM/OpenBLAS/other notices or future installer obligations. No wheels, weights,
private signals or Spleeter vendor code are shipped in Git or either application distribution.
The separately documented drum activation helper is the explicit source-code exception below.
See [primary evidence and fixed notice links](research/2026-10-16-spleeter-runtime.zh-CN.md).

The [Basic Pitch candidate adapter](BASIC_PITCH.zh-CN.md) uses an explicitly prepared
private Windows x64/CPython3.11.16 CPU runtime: Basic Pitch0.4.0 at
`9991303bba609a3b93089d13ec80d1d495083596`, ONNX Runtime1.23.2 and 40 other fixed PyPI
archives, plus a separately pinned official FlatBuffers license. Full URLs, sizes,
SHA-256s, notices and source-to-wheel hashes are in `integrations/basic_pitch_pins.json`.
That isolated runtime adds no core dependency/lock change or Basic Pitch vendor/model
content in distributions.
This curated no-TensorFlow recipe deliberately differs from upstream Python3.11 defaults.
Actual import failure established the undeclared `pkg_resources` dependency of resampy;
setuptools80.9.0 is fixed for that runtime, without running a build/setup entry point.
The Pretty MIDI source archive contributes only seven reviewed Python files and MIT
license; its soundfont and setup scripts are not installed. Two exact startup/cache
members plus the setuptools `distutils-precedence.pth` hook are omitted (three in total).
All remaining wheel/native/bundled notices stay private, including
NumPy/SciPy bundled terms and SoundFile/soxr LGPL obligations. Local use is not installer
redistribution acceptance. In particular, setuptools' vendored autocommand2.2.2 includes
LGPLv3 terms despite the distribution's MIT metadata; all actual notices are retained.
The pin's license label is a distribution declaration, not a replacement for those terms.
The source/license/model decision trail is in the
[primary-source audit](research/2026-10-16-audio-model-backends.zh-CN.md).

The [compressed-audio integration](COMPRESSED_AUDIO.zh-CN.md) explicitly provisions
SoundFile 0.14.0 / libsndfile 1.2.2, NumPy 2.3.5, CFFI 2.0.0, pycparser 2.23 and
typing_extensions 4.16.0 into a private wheel tree, never the core environment.
`codec_wheels.json` pins all twelve official wheels for Windows/Linux x86_64 and
CPython 3.11.16/cp311 or 3.14.7/cp314, plus upstream revisions/native payload hashes.
No project dependency or lock changes. All wheel notices remain in the isolated tree;
BSD/MIT/PSF wrapper licenses do not replace libsndfile/codec LGPL obligations or
NumPy's bundled-library notices. No native binary or upstream source is distributed
in this repository/package; installer redistribution/source/replacement acceptance
remains pending. Actual runtime verification includes complete payload and real native
path/version/capability handshake; file presence alone never grants readiness.

The [first M2 decoder](AUDIO_DECODE.zh-CN.md) adds no dependency, native library or
process launch. Original Python `struct`/integer code preserves PCM samples, with current
interpreter and adapter file identities in each report. SoundFile 0.13.1/libsndfile was
researched only; it is not installed, selected or included in the lock/distribution.
Native licensing/notices, exact platform runtime and compressed timing qualification
remain prerequisites for a future compressed-input slice.

The [explicit routing slice](FL26_EXPLICIT_ROUTING.zh-CN.md) adds no dependency or vendor
implementation. Factory tempo-automation structures were examined only in private probes;
their old declared version does not establish FL26 compatibility. Proprietary templates,
plugin state, DLLs and audio remain local, outside Git and distributions.

## Required foundation

The [control evidence](FL26_CONTROL_EVIDENCE.zh-CN.md) adds no dependencies. It uses
original struct/Fraction analysis and the installed, hash-pinned FL26 CLI only for
private authorized probes. Vendor SDK/constants and factory templates were read
locally; no vendor source, plugin state, MIDI/audio or private FLP is distributed.

The exact [performance preparation](NONINTERACTIVE_PERFORMANCE.zh-CN.md) uses the
existing Pydantic/Mido contracts plus standard-library `fractions`/`bisect`. It introduces
no dependency, optional backend installation, host bridge or lockfile change.

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

The dev group adds tooling and the same pinned optional Qt runtime for real GUI tests
and type checking; CLI-only end-user requirements do not include Qt. No audio ML stack,
MCP SDK or upstream DAW parser is imported by the foundation. New dependencies require
a concrete use and review.
Track-aware import includes a local timing compatibility check for mido 1.3.3's
unknown-metadata delta loss; see [MIDI import](MIDI_IMPORT.md). Regression fixtures
must remain when changing mido versions.

## Optional prerequisites

The [desktop workbench](GUI.zh-CN.md) adds optional `gui` extra
`PySide6-Essentials==6.12.0` (and exact matching shiboken6 via the lock). Only
QtCore/QtGui/QtWidgets are imported. CLI-only installation remains independent.
Module licensing/third-party notices and standalone redistribution gates are recorded
in that document; MIT does not relicense Qt, and no Qt binary is vendored.

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
The explicit `prepare-project` offline workflow also consumes those configured cleanup
preferences and records the selected active views; it requires disabled backends and
adds no dependency. `verify-preparation` replays the same declared choices from originals.
Faithful arrangement requires no additional dependencies: PPQ and effective-map
comparison use Python integer, `math.lcm` and `fractions.Fraction` arithmetic.
Arrangement options belong to the explicit API/CLI; `arrange` does not load project
YAML or apply cleanup itself.
Store credentials only in the operator's environment/secret store; no key fields exist.

The optional `--fl26-read-only` Music2DAW provision variant uses the same upstream SHA,
SDK 10 and resolved DryWetMidi 8.0.3, in another private directory. It adds no Python
dependency or lock change. Original/adapted parser and modification notice hashes join
the artifact manifest; upstream GPL notices stay with that local derived installation.
Only the original Python adaptation recipe is included in this package; backend C#
files, binaries and private reports are excluded. See [adaptation evidence](FL26_BACKEND_ADAPTATION.md).

The original [MCP discovery client](MCP_DISCOVERY.md) uses the stdlib and existing
Pydantic, without an MCP SDK or server dependency. Its explicit stdio transport requires
an independently audited/authorized external startup argv; none is configured by default.
No real backend/DAW startup or installation is part of its synthetic offline tests.

Integer PCM render comparison uses standard-library `wave`, integer decoding, streaming
SHA-256 and `math`; no FFmpeg, DSP/ML download or additional Python dependency is added.
It requires matching, already aligned uncompressed integer WAV inputs and provides
numerical measurements only. See [format/tolerance limits](RENDER_COMPARISON.zh-CN.md).

Decoded MIDI comparison uses the existing locked mido/Pydantic and standard-library
Fraction, with no new dependency or lock changes. Authorized private FL26 routing probes
used installed proprietary MIDI Out/Fruity LSD and Windows DirectMusic/GM resources;
none of those presets, plugins, banks or experiment files are distributed. Local file
presence does not establish redistribution rights. See [evidence and scope](MIDI_EVENT_COMPARISON.zh-CN.md).

The [Windows output prerequisite](HOST_READINESS.zh-CN.md) uses original standard-library
ctypes/COM interop in a separate ordinary Windows x64 CPython3.11.16/3.14.7 process.
It adds no package/lock dependency, downloaded driver or redistributed implementation.
Selected loaded Windows System32 API files (kernel32/ole32/MMDevApi) are identified and
hashed per invocation; these Windows components remain in the user's OS installation,
not the distribution. Their identity is local evidence, not one universal Windows pin
or a complete native dependency/driver audit. No audio streams or settings are changed.

The [rhythm backend](BEAT_ANALYSIS.zh-CN.md) separately pins19 Windows CPython3.11.16
wheels and official final0 weights; no core or lock dependency changes. Versions:
beat-this1.1.0, torch/torchaudio2.11.0+cpu, numpy1.26.4, soxr0.3.7,
rotary-embedding-torch0.6.4, einops0.8.0, beartype0.18.5, colorama0.4.6,
filelock4.2.0, fsspec2026.9.0, jinja2 3.1.6, markupsafe3.0.4, mpmath1.3.0,
networkx3.6.1, setuptools81.0.0, sympy1.14.0, tqdm4.66.4, typing-extensions4.15.0.
Code/weights are MIT; dependencies include BSD variants, Soxr LGPL2.1+,
tqdm MPL2.0/MIT and typing-extensions PSF2.0. Complete actual bundled notices
and artifact hashes are retained in `integrations/beat_pins.json`; wheels/models
are not distributed. Training-data rights are separate from code licensing.

The [isolated MCP adoption audit](FLSTUDIO_MCP_AUDIT.zh-CN.md) separately builds the
original Music2DAW MCP at the existing pin with SDK10.0.401/runtime10.0.12/MCP1.4.1,
and installs live candidate e6eff37 with Python3.11.16/FastMCP2.14.5/MCP1.30.0 into a
new private locked environment. No core dependency/lock change, optional ML stack,
virtual MIDI driver or FL controller installation occurs. Actual resolved notices,
locks and runtime/artifact identities remain local; genuine discovery does not grant
host/tool execution. See the audit for the package/module version discrepancy and
redistribution-notice limitations.

## Drum encoder and distribution notices

The [selected encoder-only drum runtime](DRUM_INFERENCE.zh-CN.md) reuses13 exact official
wheels from the prior audited rhythm dependency set, without core ML dependencies:
einops0.8.0, filelock4.2.0, fsspec2026.9.0, Jinja2 3.1.6, MarkupSafe3.0.4,
mpmath1.3.0, networkx3.6.1, NumPy1.26.4, setuptools81.0.0, sympy1.14.0,
Torch/Torchaudio2.11.0+cpu, typing-extensions4.15.0. Actual wheel notices/omissions,
source/config/checkpoint/member hashes, full330tensor geometry and exact import-only
activation patch are pinned in integrations/drum_pins.json. Selected source is Apache-2.0;
ConvNeXt's separate Meta MIT blob is explicitly required. The source and model remain
local, with no automatic download or weights/native dependency distribution.

The application does distribute integrations/drum_activations.py derived under Apache-2.0.
It includes full grant and change attribution in integrations/notices and distribution
license-files, so packaged SPDX is MIT AND Apache-2.0; the original root MIT grant for
first-party files is unchanged. Installed-wheel smoke verifies the actual metadata and
complete license bytes. This does not relicense external dependencies/training music or
complete the independent installer/model redistribution audit. New artifact preparation,
actual native handshake and all musical/job/writer qualifications remain distinct.
