# Risk register

Recomputed MP3 CRCs do not prove valid reservoir references: the pinned decoder can
silently replace unavailable main data with silence while preserving frame count and
reporting zero error. Complete side-info/main-data extent checks now run before native
execution, preserve legitimate nonzero reservoirs and hash audio side-info in source
order. Synthetic protected/unprotected and real native adversarial regressions cover
this concealment case; arbitrary Huffman semantics remain outside that structural proof.

Compressed-audio risks and mitigation are detailed in
[fixed codec qualification](COMPRESSED_AUDIO.zh-CN.md): native success can hide
truncated MP3 and appended/concatenated FLAC, so complete source-frame/CRC coverage
is required first. Unproven MP3 delay/padding blocks; qualified native replay is not
an uncompressed MP3 truth oracle. Current payload, trusted executable, library path
and versions are rechecked before/after work; malicious/native-library vulnerabilities
are not contained by an OS sandbox. LGPL/codec/NumPy redistribution requirements and
future installer library replacement/source notices remain explicit M5 gates.

The [explicit MIDI routing slice](FL26_EXPLICIT_ROUTING.zh-CN.md) rejects incomplete
coverage, destination aliases, receiver/port namespace collisions and channel rewrites.
Complete declarations do not attest actual receiver delivery. Exported program values,
selected audio responses and inactive factory automation candidates cannot establish
whole-song fidelity; all timing, host and writer restrictions remain in place.

| Risk | Impact | Mitigation / future gate | Current status |
| --- | --- | --- | --- |
| PCM conversion loses low bits or shifts channels/time | Analysis begins from altered music | Binary64 exact power-of-two normalization, unchanged frame clock/order and independent inverse integer-byte comparison | All integer widths/extrema and boundary impulses tested; no music/host qualification |
| Rehashed decoded evidence mistaken for sample fidelity | Changed audio reused on resume | Reconstruct current source preflight and all original integers, verify runtime/code/output identities before/after | Decode verifier rejects forged sample data; old completed evidence cannot be silently refreshed |
| Cancelled/partial decoded WAV reused | Missing tail or invalid container promoted to completion | New attempt directory, independent whole-file validation, durable completion only after verification; retain failed candidates | Cooperative block-boundary cancellation; current I/O may finish first; compressed formats remain blocked |
| Audio compensation changes original MIDI events | Correct-looking onsets conceal moved tempo points | Compare independent MIDI event positions and exact clocks; never compensate source ticks from one render | Minus-one-tick audio probes align selected onsets but export the moved tick; writer blocked |
| MIDI export treated as a receiver log | Extra transport controls or inferred channels/programs silently accepted | Preserve every occurrence, ordered tracks and current inputs; separate export and audio evidence | Selected port/volume audio response verified; full program/channel routes unverified |
| Exit zero without output | Failed background run reported as success | Require fresh file, parse, hashes and before/after input identities | Sandbox and incorrect MIDI argv cases exposed; no-output attempts retained as failures |
| FL26 REC structure confused with exact playback | Step timing differences or misrouted CC/program messages | Separate selected-field observations, source-replayed encoding analysis and unconditional writer block | 14 private renders: scalar/event PCM equality; stepped timing differs at 96/960 PPQ; MIDI destination unverified |
| Noninteractive MIDI preservation mistaken for playable FLP | Lost tempo/control behavior despite retained JSON | Exact event-time/tempo-scalar checks, current-source replay and literal blocked execution; prove automation addressing/routing separately | Performance compilation implemented; faithful variable-tempo/control FLP remains blocked |
| Background rendering mistaken for headless import/save | Stalled MIDI import or false host acceptance | Bound owned process lifetime; never send interface input; distinguish existing-FLP render from MIDI-to-new-FLP | Reference rendering verified locally; MIDI test timed out, import/save unverified |
| FLP format/version drift | Corrupt or subtly altered project | Pin backend and FL version; preserve unknown events; parse and open copied output | No FLP writes |
| MIDI transcription errors | Wrong pitch, rhythm or instruments | Prefer official MIDI; retain source timing; uncertain AI output reviewed separately | No inference |
| Upstream instability | Tool/schema changes or broken installs | Pin commits, isolated adapters, capability discovery and contract fixtures | Pinned isolated inspection verified; writer remains blocked |
| Missing plugins/presets/samples | Silent or changed rendering | Template dependency manifest, plugin/version checks, manual listening | No plugin claims |
| File corruption or overwrite | Loss of source/template | Read-only inputs; exclusive destinations; future hash checks, temp-write/readback | Basic guards tested |
| Licensing/redistribution | Incompatible code/model/template distribution | No upstream copying; inspect per-component licenses before integration/release | Existing MIT retained |
| Unsafe paths/links | Work outside workspace | Resolve config paths, reject overlaps/escapes; skip discovery links | Tested guards; concurrent hostile filesystem changes not protected |
| Malformed or huge media | Parse failures or resource exhaustion | Per-file diagnostics; future limits/sandboxing for untrusted imports | Basic local trusted-file scope |
| WAV codec/header limitations | Metadata unavailable or incomplete | Clearly report unsupported/corrupt headers; future full decode validation | No deep audio claims |
| Filename matching uncertainty | Incorrect stem association | Require one MIDI and WAV per case-insensitive stem; warn on ambiguity | File-level matches only |
| MIDI timing differences | Misaligned arrangement | Preserve raw delta/absolute ticks and tempo/meter provenance; future explicit PPQ conversion | Type 0/1 import only; Type 2/SMPTE rejected |
| Ambiguous or incomplete note pairing | Incorrect derived duration | FIFO with warnings for overlapping channel/pitch; retain unmatched raw events without invented durations | Synthetic edge cases tested |
| Conflicting timing maps | Ambiguous tempo or meter | Retain all changes in tick/track/event order and warn; no silent resolution | Imported with provenance |
| Decoder timing defects | Silent shifts after unknown metadata | Recover source deltas for unknown-meta files; retain independent raw-byte timing fixtures | mido 1.3.3 gap covered |
| Cleanup changes musical intent | Lost ornamentation or timing feel in derived notes | Default-off operations, explicit tick thresholds/grid, full before/after audit and untouched source events | Synthetic boundary fixtures; no musical-fidelity claim |
| Confusing source and derived events | A future writer exports the wrong note view | Source events/end_tick stay original; active notes are separate, with original fields retained | JSON representation only; no MIDI writer |
| PPQ precision loss | Timing drift or vanished short notes | Exact LCM default; explicit target/rounding policy; reject collapsed positive notes and map collisions | Integer/rational conversion tested |
| Incompatible effective timing maps | Inputs play at different intended timing | Compare entire beat-domain functions including defaults; explicit authority with warnings for overrides | Strict default; source evidence retained |
| Provenance unit confusion | Source ticks mistaken for arrangement ticks | Per-track source PPQ, note origins, full input snapshots; current ticks use arrangement PPQ | Documented/round-trip tested |
| Excessive common PPQ or snapshot size | Large JSON or downstream DAW limits | Keep this representation DAW-independent; future backend must declare PPQ/size constraints | No binary-format compatibility claim |
| Incorrect explicit role selection | Misleading instrument intent metadata | Exact indexed selectors; reject unmatched/overlapping rules; retain config hash and source snapshots | No name/program inference |
| Confusing GM and source numbering | Accidental future channel/program rewrite | GM hints 1..128, source channels 0..15; mapping has no destination channels and preserves raw program events | Annotation-only; plugin status unverified |
| Backend timing/performance gaps | Flattened tempo/meter maps or omitted CC/bend/sustain | Music2DAW pin accepts one tempo and no arbitrary MIDI event stream; declare and reject unsupported inputs, validate tempo precision and exact template-PPQ conversion | Source-assessed; no writer |
| FL IDs mistaken for source MIDI channels | Lost channel identity or wrong instrument binding | Exact indexed source selectors, separate destination IDs, full arrangement/sidecar and one-to-one binding checks; inferred MIDI export is not a fidelity oracle | Explicit dry-run contract tested; no routing or writer |
| Dry-run preview mistaken for an executable build | Unsupported events, template content or instrument state silently lost | Block inexact PPQ, unsupported maps/events and missing evidence; preserve full snapshots and diagnostics; always disable execution | Every plan is blocked or review_required; structure and audible compatibility unverified |
| Backend overwrite and inherited content | Existing output loss, old notes/automation or cropped clips remain | Byte-linked inventories, exact bound-pair/clip checks and blocking diagnostics; future private staging/exclusive publish and readback | Inventories/v2 checks implemented; unknown semantics blocked; no writer |
| Inventory coverage mistaken for complete FLP semantics | Hidden plugin/track behavior or unknown automation changes playback | Narrow reader/version profile; retain opaque hashes/raw known records; partial/unsupported evidence blocks; preserve unconditional execution prohibition | Synthetic known layouts verified; real template/host and opaque semantics remain open |
| FL26 successful-but-incomplete backend parse | Empty notes/clips and default tempo mistaken for real data | Keep independent local/backend summaries with completeness gates and mismatch provenance; never substitute or trust exit 0 alone | Actual private input reproduces mismatch; exact read-only profile added; FL26 writer blocked |
| Playlist encoded ID overflow or inconsistent bases | Future backend throws or changes clip identity | Check first-record base plus every target Pattern against uint16 and reject mixed bases | Review finding reproduced and fixed with synthetic cases |
| Incomplete template/host evidence | Cannot establish plugin state or audible compatibility | Template rights/hash/version/dependency manifest, isolated pinned inspection, later FL Studio open/listen | Private real FL26 template verified read-only; dependency versions/availability and host acceptance remain open |
| Dependency labels mistaken for ownership or availability | Wrong instrument/sample or stale rack assignment to mixer effect | Byte-linked declarations, strict raw text, cleared mixer-context hints; no path expansion or external reads | Selected declarations only; owner/version/format/availability/rights unverified |
| Local target match mistaken for writer readiness | Backend omissions or unhandled source content silently accepted | Separate local binding evidence, complete source hash/pairing checks, exact PPQ and ambiguity blockers; all writer gates retained | Permanently blocked assessment; no executable edit intent or FLP output |
| Modified optional backend or misleading parse success | Unreproducible/unsafe inspection or false compatibility claims | Full reviewed source pin, isolated generated locks and artifact hashes, before/after checks, fixed inspect-only arguments and explicit unverified compatibility | Provisioning and synthetic real parsing verified; hashes are not authentication or OS isolation |
| MCP tool overclaim | Missing operations or unverified mutations | Handshake, tool listing, snapshots/readback and audible checks | All connections unverified |
| Reproducibility gaps | Different outputs after rerun | Locked dependencies, stable ordering, preserve configs and source/backend fingerprints | Synthetic eligible bundle bytes deterministic; no real playback claim |
| Restricted writer mistaken for real FL26 compatibility | Unresolved user content or dependencies silently serialized | Separate policy/intent, strict events/prototypes/maps, backend agreement, source replay, byte-budget and independent output checks | Synthetic positive output only; actual private template explicitly blocked |
| Output publication races or incomplete sidecars | Existing files overwritten or orphan FLP treated as successful | Windows no-replace whole-bundle publication, exclusive new files, staged/final identity/hash checks, failure reports and retained new artifacts | Trusted local filesystem only; no hostile same-user/crash-durability guarantee |
| Prior arrangement rounding hidden by final PPQ | Original timing loss promoted to exact output | Reject rounding-enabled arrangements before encoding; check converted endpoints and original source replay | Independent review repro covered by regression |
| Adapted parser mistaken for complete FL26 support | Correct counts conceal wrong crops/lanes or editor assumptions | Separate inspection-only profile/source/recipe hashes, retain old report and raw records, exact-build preflight; leave field/host/writer gates unchanged | Selected tempo/count agreement verified with genuine runtime; opaque semantics and upstream editor remain unverified |

Owners: importer/validator maintainers for media/path risks; adapter maintainers for
DAW/version risks; project maintainers for dependencies and redistribution decisions.
Revisit before each roadmap phase and whenever upstream revisions change.

GUI risks: the [desktop workbench](GUI.zh-CN.md) uses real stage snapshots and explicit
blocked explanations. Long I/O stays off the UI thread; cancellation is cooperative and
close waits for a boundary, without thread/process termination. Root changes are disabled
while busy; corrupt selections clear previous action targets. Offscreen tests/rendering
do not prove real user interaction, accessibility, host behavior or release quality.
Optional Qt is exact-pinned, dynamically installed with upstream notices retained; an
independent installer still needs its complete module/source/redistribution audit.
Phase 3's [assessment and blockers](FLP_BACKEND_ASSESSMENT.md) distinguish source
support from runtime and audible compatibility. The subsequent
[read-only inspection slice](TEMPLATE_INSPECTION.md) passed isolated build and synthetic
parse checks; real template, plugin and audible compatibility gates remain open.
The [binding/dry-run slice](BUILD_PLANNING.md) adds deterministic preview checks and
current-file fingerprints without changing those gates or invoking a writer.

The [genuine MCP audit](FLSTUDIO_MCP_AUDIT.zh-CN.md) separates protocol availability
(5/67 tools) from host readiness. Untrusted tool annotations, the live candidate
package1.0.0/module0.3.0 discrepancy, missing open/save/zoom/crop/reopen coverage,
Python audit-hook/native-FFI limits and incomplete redistribution notices remain
explicit blockers for broader adoption. No tools/resources/bridge calls occurred;
all host and writer gates remain unchanged.
