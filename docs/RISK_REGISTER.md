# Risk register

| Risk | Impact | Mitigation / future gate | Current status |
| --- | --- | --- | --- |
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

Owners: importer/validator maintainers for media/path risks; adapter maintainers for
DAW/version risks; project maintainers for dependencies and redistribution decisions.
Revisit before each roadmap phase and whenever upstream revisions change.
Phase 3's [assessment and blockers](FLP_BACKEND_ASSESSMENT.md) distinguish source
support from runtime and audible compatibility. The subsequent
[read-only inspection slice](TEMPLATE_INSPECTION.md) passed isolated build and synthetic
parse checks; real template, plugin and audible compatibility gates remain open.
The [binding/dry-run slice](BUILD_PLANNING.md) adds deterministic preview checks and
current-file fingerprints without changing those gates or invoking a writer.
