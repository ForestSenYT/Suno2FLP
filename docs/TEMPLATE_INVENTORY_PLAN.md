# Read-only template inventory implementation plan

**Goal:** extend existing inspection and dry-run planning with byte-linked note,
playlist, automation and crop evidence; never write or execute an FLP build.

**Architecture:** an original Python reader consumes the already-read template byte
snapshot. It inventories event framing and the narrowly assessed FL 25.1.2.4896
layouts without modifying or copying backend code. Existing Music2DAW inspection
remains the independent summary source. Planning stays process-free and retains the
complete inventory; its file wrapper additionally compares a fresh local scan.

**Constraints:** same exact Music2DAW pin; no new dependencies or backend changes;
source channels/events/timing stay unchanged; no edit/export/launch/plugin action;
all plans remain non-executable and compatibility unverified. Existing report schema
can load with no inventory, but such evidence must block the new capability profile.

**Review focus:** malformed chunks/variable-length prefixes; repeated note/playlist
events; ambiguous legacy/routing layouts; nonfinite or fractional crop/automation
values; modified or incomplete saved inventories. Preserve bytes/offsets/hashes and
fail or block explicitly, without rounding, assuming absence or clearing content.

- [x] Add failing original synthetic tests for inspector inventories and framing.
- [x] Add typed inventory contracts and a pure, bounded read-only event scanner.
  Retain event indices, absolute offsets, payload hashes, record bytes, all note
  attributes, clip links/flags/crop float bits and automation payloads. Decode only
  assessed layouts; keep ambiguous/unsupported content explicit.
- [x] Integrate scanning into inspection; cross-check summary counts/IDs. Keep
  before/after template and backend verification and existing output guards.
- [x] Add failing dry-run cases, then strengthen checks for absent/stale inventory,
  inherited unbound notes/clips, repeated event replacement, automation, crops/mutes,
  unsupported layouts and missing fine-tempo events. Preserve candidate notes and
  all evidence; never invent a deletion/merge policy or truncate floats to ticks.
- [x] Recompute inventory from actual bytes in file-based planning, without a
  backend call. Upgrade the capability/algorithm profile and document migration.
- [x] Run offline and opt-in real synthetic suites on Python 3.11/3.14, static checks,
  independent read-only review, package/archive and installed CLI smoke. Update
  usage, architecture, roadmap, dependency/integration evidence and remaining gates.

No commits or pushes are part of this user-authorized implementation slice.

Completed evidence: 299 passed/1 Windows permission skip on each local interpreter
with real backend enabled; offline 295 passed/5 explicit skips. Static checks and
installed-wheel positive/blocked/freshness/output checks passed. Independent review
caught an encoded Pattern overflow gap, fixed with failing/passing regression cases.
See [inventory documentation](TEMPLATE_INVENTORY.md) for retained evidence and limits.
