# Suno2FLP agent guide

## Purpose and boundaries

For delivery scope, quality acceptance or GUI/audio-only work, read
docs/DELIVERY_ROADMAP.zh-CN.md and its linked product design first; distinguish the
active delivery target from implemented capabilities and preserve the design's status.
Before creating a development branch, publishing or merging a PR, follow
docs/GITHUB_WORKFLOW.zh-CN.md: use a new slice from current main, bind review to the
actual head, verify current CI and merge only that reviewed head.

Suno2FLP reconstructs official Suno MIDI and reference stems into editable FL Studio
projects. Implemented scope: foundations, Phase 1 MIDI import/cleanup, and Phase 2
faithful arrangement construction plus explicit role mapping, and Phase 3 isolated
backend provisioning/read-only template inspection and explicit binding/dry-run planning.
The inventory slice adds read-only note/clip/automation/crop evidence and v2 planning gates.
Read docs/ARCHITECTURE.md and the relevant
roadmap phase before expanding behavior. AI inference stays separate from deterministic
processing; official MIDI has priority.

`core` owns Pydantic contracts/errors/config/path guards. `importer` reads local assets
and track-aware MIDI. For timing, pairing or import changes, read docs/MIDI_IMPORT.md;
preserve source event order, delta/absolute ticks, source hash and tempo/meter provenance.
For cleanup changes, read docs/MIDI_CLEANUP.md: operations default off, source events
stay unchanged, and every derived change requires a before/after audit with original
timing. Quantization changes starts only on an explicit tick grid. `midi_processor`
implements its protocol. For arrangement changes, read docs/ARRANGEMENT.md: preserve
input snapshots and timing units, keep conversion exact by default, and explicitly
resolve timing conflicts/view selection. `arrangement` implements faithful mode;
for role-mapping changes, read docs/INSTRUMENT_MAPPING.md: use exact source selectors,
preserve channels and full config provenance, reject overlaps, and keep GM/plugin
hints separate from availability or routing. Mapping performs no plugin/DAW actions.
Generic `FLPBuilder` and `daw_controller` still expose protocols; `flp_builder` implements
pure planning/readiness and a separate restricted native writer file workflow.
For policy, encoding, output publication or verifier changes read docs/FL26_WRITER.md.
Require exact source reconstruction, explicit reviewed prototypes, strict compatibility
gates, independent output checks and new Windows bundles. Never promote old blocked
plans/readiness into writes or bypass unresolved real-template evidence.
`validator` provides structural checks; `integrations` implements isolated pinned
Music2DAW provisioning and read-only inspection. Read docs/TEMPLATE_INSPECTION.md:
verify backend and template hashes, call only inspect, fail explicitly on missing or
inconsistent prerequisites, and keep FL Studio/plugin compatibility unverified.
Read docs/BUILD_PLANNING.md for planning: exact source selectors and separate target
IDs, one-to-one bindings, exact PPQ conversion, full provenance snapshots and explicit
capability blockers. Preserve the unconditional execution prohibition. The file wrapper
rechecks current backend/template hashes; planning must not invoke the backend.
Read docs/TEMPLATE_INVENTORY.md before changing inventory: retain byte offsets, event
indices, raw records and float bits; do not truncate crops/automation to ticks or infer
unknown layouts. Partial/unsupported/missing inventories block v2; file planning must
regenerate inventory from current bytes. No clearing or merge policy is implicit.
For FL26 read docs/FL26_READ_ONLY.md: use only exact 26.1.7.5654 profile, require
preceding version evidence, retain event headers/rules and all 88-byte records. Keep
local facts and backend results separate, flag incomplete successful parses, and
preserve all old preview writer blocks. The new writer has separate explicit eligibility;
private user FLPs must stay ignored and unchanged.
Keep dependencies pointing inward to core. CLI coordinates services without embedding
backend logic. Implement only the roadmap slice explicitly authorized by the user.

## Change and file rules

- Prefer small, typed, modular changes with reproducible inputs and diagnostics.
- Never modify source audio or MIDI in place; write new intermediates exclusively.
- Never overwrite an FL Studio template or existing output. Resolve destinations and
  check links/overlaps; future builders must compare source/template hashes and reparse
  outputs before reporting success. A real FL Studio open/listening check is required
  for compatibility claims. No FLP binary changes are implemented in Phase 0.
- Keep credentials outside version control. Avoid unnecessary dependencies and model
  downloads. Preserve Git history and user files. No destructive cleanup without scope.
- Write behavioral tests for new features using tiny synthetic, original fixtures.
  Retain timing/provenance; external integration tests must be opt-in and skip clearly
  when prerequisites are missing. Default tests must run offline without a DAW/GPU.

## Validation before success

After `uv sync --locked`, run `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, and `uv run mypy src`. For packaging changes also run
`uv build` and smoke-test the installed CLI. In restricted environments a writable
`--basetemp` under `.pytest_cache` may be needed. Confirm actual output/exit codes;
report limitations and any skipped checks. Keep documentation synchronized with code.

## Adding an integration

Verify upstream capabilities, license, runtime and pinned revision first; record them
in docs/INTEGRATIONS.md and docs/DEPENDENCIES.md, with risks in docs/RISK_REGISTER.md.
Implement the relevant protocol under `integrations` using core models and typed errors.
Keep incompatible/heavy runtimes isolated. Discover MCP tools through a real handshake;
never infer successful connectivity from executable presence or fabricate success.
Add offline contract tests and separately marked opt-in integration tests with explicit
missing-prerequisite skips. Update README capabilities and roadmap only when behavior
is implemented and verified. Document changes in units, schemas and compatibility.
