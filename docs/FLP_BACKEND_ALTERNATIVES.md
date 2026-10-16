# Phase 3 FLP backend alternatives: source assessment

Audit date: 2026-10-15. This is a fresh read of pinned upstream source, package
metadata, licenses and tests, not a runtime or FL Studio compatibility test.
Firecrawl supplied the initial source reads; its shared rate limit required
read-only GitHub raw/API requests for the remainder. Downloaded reference source
is confined to ignored `.tools/phase3-alternatives-source/`. No upstream code was
installed or executed, no FLP was generated or changed, and no plugin/DAW action
was performed.

## Recommendation

Keep separately provisioned Music2DAW as the primary **candidate for a controlled
template experiment**, subject to its companion source assessment and explicit
runtime/template gates. PyFLP is useful as a secondary inspector and a possible
template-edit fallback, but its audited model API leaves substantial project
construction work to the adapter. Do not select demixer's current writer for
faithful Phase 3 reconstruction: its fixed timebase, seconds-based conversion,
silent note channels and lack of template preservation conflict with the current
requirements. This ranking is an engineering inference from the evidence below;
it does not establish that any backend works with the user's FL Studio build.

Music2DAW's proposed isolated process boundary remains a deployment choice, not a
license exemption. Its separate evaluation should settle the exact edit surface,
new pattern/channel limitations and template-state behavior before adoption.
[Music2DAW pinned source](https://github.com/jihadkhawaja/flstudio-mcp/tree/6def9463d6fa8636bbc81010581318a39c47d3c4).

## Verified revisions and runtime constraints

| Candidate | Verified pin | Declared runtime and packaging |
| --- | --- | --- |
| PyFLP | `f937126b888ce94271bfea631b89166c74056530`; commit dated 2023-07-11 | Python >=3.8; alpha classifier; `construct-typing>=0.5.6`, `sortedcontainers>=2.4.0`, `typing_extensions>=4.6.1`, conditional `f-enum`; setuptools/SCM-generated version. Lower bounds do not provide a reproducible resolved environment. |
| demixer | `7865ce616d4f8d3755078bbc30d4bd2da5b0a70a`; commit dated 2026-08-31 | Python >=3.11,<3.12; package 0.1.0; runtime dependency list empty. `pretty_midi`, PyFLP and soundfile appear in the dev extra. Its lockfile pins PyFLP 2.2.1. The full pipeline also needs external audio/ML provisioning. |

Evidence: [PyFLP commit API](https://api.github.com/repos/demberto/PyFLP/commits/f937126b888ce94271bfea631b89166c74056530),
[metadata](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyproject.toml);
[demixer commit API](https://api.github.com/repos/revoydotdev/demixer/commits/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a),
[metadata](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/pyproject.toml),
[lockfile](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/uv.lock),
[installation limitations](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/README.md#requirements-and-current-installation-status).
The SHA responses verify these objects exist; this audit does not equate a pin
with the latest release or with a successful install.

## PyFLP: template inspection/editing foundation

- **Read/save:** `parse()` checks FLhd/FLdt structure, size, format and an allowed
  PPQ set, then constructs ordered events. `save()` rebuilds the header, channel
  count and every event into the supplied destination with `wb`. It supplies no
  no-overwrite/hash guard. The public entry points demonstrate parsing an
  existing project and saving it; they do not provide a supported blank-project
  factory. Raw event construction is possible in principle, but must not be
  advertised as a proven fresh-project backend.
  [Parser/writer](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/__init__.py).
- **Notes and new patterns:** notes have writable position, length, key, velocity,
  rack-channel and MIDI-channel fields in a 24-byte record. `Pattern.notes`
  yields existing note models. Pattern identifiers are one-based; collection
  indexing is zero-based. The audited `Patterns` and `ChannelRack` collection
  models do not expose high-level add-pattern/add-channel operations. Adding a
  new structure would require assembling valid lower-level events, channel IDs,
  pattern delimiters and placement, rather than calling a complete constructor
  that maintains those relationships.
  [Pattern model](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/pattern.py),
  [channel model](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/channel.py),
  [event insertion/list structures](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/_events.py).
- **Playlist and channel links:** existing playlist items expose position/length
  and channel/pattern setters. The latter update `item_index` to the channel IID
  or pattern IID plus `pattern_base`. Track indexes are reversed; the model
  distinguishes 199-track older projects from 500-track newer projects and
  recognizes 32/60-byte playlist records. It contains explicit TODOs about older
  arrangement grouping. Source support for these layouts is not a test of a
  particular FL Studio version. New items still require valid payload/event
  construction and ID consistency.
  [Arrangement model](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/arrangement.py).
- **Timing:** accepted PPQs at this pin are 24, 48, 72, 96, 120, 144, 168, 192,
  384, 768 and 960. The PPQ setter only changes the stored value. Upstream
  expressly says timing recalculation is outside PyFLP's scope. A future adapter
  should keep template PPQ fixed and perform exact rational conversion or reject
  an unrepresentable timing result under an explicitly selected policy.
  [Project PPQ contract](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/project.py#L384-L415).
- **Opaque plugin states:** unknown data events use raw bytes; unrecognized
  native plugins fall back to that representation. VST wrapper state and
  unknown subevents have byte payload paths, while recognized structures are
  parsed and rebuilt. That makes opaque retention plausible, but does not prove
  byte preservation for every typed event, future layout or plugin. Verify
  unchanged payload hashes and event order for each approved template; do not
  infer that plugin presets are portable or loadable from a successful parse.
  [Plugin dispatch/state](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/plugin.py),
  [event serialization](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/_events.py),
  [save path](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/__init__.py).

One concrete runtime warning comes from demixer's pinned tests: they patch private
PyFLP enum maps to work around a documented PyFLP 2.2.1 / CPython 3.11.15 parser
failure. This is upstream test-source evidence, not a reproduction here, and does
not prove every PyFLP revision fails. It does mean `requires-python>=3.8` is
insufficient evidence for compatibility with a chosen modern interpreter.
[Workaround and explanation](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/tests/test_project_flstudio.py#L32-L51).

## demixer: narrow fresh-generation writer

The pinned module builds FLhd/FLdt bytes without reading a template. It writes
FL version `21.0.3.3517`, PPQ 96, one global BPM, time-signature beat field 4, 500 track records
and pre-FL21 32-byte playlist records. It creates a Sampler referring to each WAV
and a separate silent Sampler for each stem with MIDI. Each transcribed stem gets
one pattern; all clips start at zero with the same supplied duration. Pattern
clips use `20480 + pattern_id`, notes refer to the selected rack channel and
playlist track indexes are reversed. These are implemented relationships, not
proof that FL Studio accepts or plays them.
[Writer, constants and records](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/src/demixer/core/project/flstudio.py).

Its MIDI path reads notes as seconds through `pretty_midi`, then rounds
`seconds * BPM / 60 * 96`; lengths are forced to at least one tick. It merges all
instruments from one MIDI into that stem's single rack channel, sets the note
MIDI-channel byte to zero, and does not transfer source tempo/meter maps,
programs, controllers, original event order or source tick provenance. Exact
official-MIDI reconstruction is therefore not its current contract. As a simple
consequence, at matching constant BPM, one tick at source PPQ 960 becomes 0.1 destination ticks and is
rounded to zero. No plugin-state/template copy path exists in this writer.
It also opens the output with `wb`, so adopting it directly would violate the
no-overwrite boundary.
[Conversion and output path](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/src/demixer/core/project/flstudio.py).

The inspected tests reparse synthetic output with PyFLP and assert header/tempo,
channel count, note/pattern contents and sample paths. They do not assert playlist
placement/linking or run FL Studio. The separate piano-roll script generator
clears the current score and injects notes; it is a DAW mutation path and is
outside this assessment's execution scope. Neither test compilation nor parser
round trips establish audible playback, native-plugin state fidelity or FL
version compatibility.
[Writer tests](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/tests/test_project_flstudio.py),
[piano-roll generator](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/src/demixer/core/project/flstudio.py).

## License evidence and remaining adoption gates

PyFLP metadata says GPL-3.0 and its source headers permit GPL version 3 or later.
The license's sections 4-6 address preservation of notices/license text, modified
source and corresponding source for object-code conveyance. demixer metadata
says AGPL-3.0-or-later; its license includes those distribution conditions and
section 13's source-offer condition for modified versions supporting remote
network interaction. The FLP module credits PyFLP as its layout reference; it is
not a permissively licensed substitute. This records upstream terms, not a legal
opinion about a future combination. Review the actual packaging/distribution
plan before copying code or bundling either backend. Process isolation alone
does not resolve those questions.
[PyFLP license](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/LICENSE),
[source notice](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/__init__.py),
[demixer license](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/LICENSE),
[demixer metadata](https://github.com/revoydotdev/demixer/blob/7865ce616d4f8d3755078bbc30d4bd2da5b0a70a/pyproject.toml).

Before any candidate becomes an implemented backend, the separately authorized
experiment must establish a reproducible runtime, suitable FL Studio build and
owned template, usable pre-created generator/channel capacity, exact timing
policy, collision-free pattern/channel/playlist links, unchanged plugin payloads
and source/template hashes, exclusive new outputs and successful reparsing. A
real FL Studio open/listen check is still required for a compatibility claim.
This audit supplies source evidence only and leaves all those runtime gates open.
