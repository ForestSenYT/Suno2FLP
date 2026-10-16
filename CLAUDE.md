# Claude Code instructions

Read and follow [AGENTS.md](AGENTS.md), the shared source of project engineering rules.
Suno2FLP provides foundations, track-aware MIDI import, opt-in deterministic cleanup
and faithful arrangements with explicit instrument-role annotations. Reinterpretation
and MCP connections remain planned. Read docs/ARRANGEMENT.md for PPQ precision,
timing-map conflict policy, note-view selection and full source provenance.
Restricted native FL26 writing now exists behind a separate policy/intent and Windows
new-bundle workflow; read docs/FL26_WRITER.md before changing it. All unresolved
evidence must still block and old previews remain non-executable. Source templates
stay immutable; structural synthetic verification does not establish host playback.
Read docs/INSTRUMENT_MAPPING.md for exact role selectors, config snapshots/hash,
source-channel preservation, GM numbering and unverified plugin hints. Mapping never
loads plugins, reroutes channels or rewrites source program changes.
Phase 3 adds explicit isolated backend provisioning and read-only template inspection;
read docs/TEMPLATE_INSPECTION.md. Verify the exact pin/artifact and before/after template
hashes; never call edit/export/launch or infer playback/plugin availability from parsing.
The next slice adds explicit bindings and dry-run plans; read docs/BUILD_PLANNING.md.
Keep source channels and provenance separate from target IDs, conversion exact and
every plan non-executable. Planning never calls the backend; its file wrapper verifies
current template/backend hashes before and after the pure calculation.
Read docs/TEMPLATE_INVENTORY.md for byte-linked note/clip/automation/crop inventories.
Preserve raw records and float bits; block absent/partial evidence, inherited conflicts,
automation/crops and unsafe encodings. V2 file planning rechecks a fresh byte scan.
Read docs/FL26_READ_ONLY.md for exact-build 3-byte event 172 / 88-byte clip support.
Retain profile/header/extension provenance and independent local/backend results;
inconsistent summaries are not compatibility success and FL26 never enables writing.
Read docs/MIDI_IMPORT.md before changing timing, pairing, or tempo/meter extraction;
retain original event order/ticks and provenance alongside derived note data.
Read docs/MIDI_CLEANUP.md before changing cleanup: keep operations default off, original
source events/timing immutable within the pipeline, and retain before/after change
records. Quantize starts only with an explicit grid; never rewrite source MIDI.

Use the `src/suno2flp` module boundaries documented in docs/ARCHITECTURE.md: core
contracts/configuration, read-only importer, MIDI processor, arrangement, FLP builder,
DAW controller, validator, and optional integration adapters. Prefer small modular
changes, typed Pydantic contracts and synthetic behavioral tests. AI inference must
stay separate from deterministic processing; preserve official MIDI and reproducibility.

Never modify input audio/MIDI in place, overwrite templates, or silently replace
existing files. Future FLP changes require new outputs, original hash checks,
parse/readback and actual FL Studio open/listening verification. Do not claim DAW
interaction without real evidence. Keep credentials out of the repository and avoid
unnecessary dependencies or model downloads.

Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
and `uv run mypy src` before declaring success; packaging changes also require
`uv build` and installed CLI smoke checks. Report actual failures/skips and blockers.

For new integrations, verify the upstream revision, capabilities, runtime and license,
use an isolated adapter implementing the appropriate protocol, negotiate capabilities,
and add offline tests plus optional external tests that skip without prerequisites.
Synchronize README, docs/INTEGRATIONS.md, docs/DEPENDENCIES.md, architecture, roadmap
and risks with the implementation. Consult AGENTS.md for the full shared procedure.
