# Explicit bindings and dry-run build planning

User-authorized Phase 3 slice: extend existing faithful arrangements and read-only
template inspection into a deterministic preview. Never invoke an editor, export,
launch, plugin loader or FLP writer. Keep project backend defaults disabled.

Design decisions:

- Bind exact input/track-position/MIDI-channel identities to existing template rack
  channel/Pattern/playlist-track IDs. Pin bindings to the exact template hash and
  backend revision. First slice is one-to-one, with no inference, merging or wildcard.
- Pure API consumes snapshots, preserves independent full copies and calculates exact
  target-PPQ note endpoints/clip lengths. Reconstruct faithful music from recorded
  source views/options to detect inconsistent arrangement provenance.
- Report supported-subset violations as blocking diagnostics: incomplete bindings,
  precision/range loss, variable tempo/meter, unsupported MIDI controls/programs,
  missing template structures, unsupported version and unsafe target instruments.
- Emit preview parts only where target ticks are representable. Plans are blocked
  or review-required; execution is always false and compatibility unverified. Summary
  inspection cannot prove all event layouts, inherited notes/automation/crops or rights.
- CLI reads arrangement/inspection/binding bytes once with raw hashes, verifies current
  backend/template fingerprints against inspection, and writes only new JSON outside
  the backend directory. Blocked plans are retained for review and return exit 1;
  invalid prerequisites/configuration create no output. Pure API performs no I/O.

Implementation and verification:

1. Tests first for exact bindings, selector/target conflicts, config hashes, complete
   snapshot/role/cleanup provenance, PPQ boundaries and capability failures.
2. Add typed contracts/YAML loader, planner and focused provenance/capability helpers.
3. Add `plan-build` CLI with fixed read-only behavior, input hashes and output guards.
4. Extend original synthetic fixtures; opt-in real inspection-to-plan test executes
   only inspect. Check offline/real tests on both Python versions, static checks,
   package/install smoke and independent read-only review.
5. Update usage, examples, architecture, dependencies, roadmap and remaining blockers.

No commits, pushes, system installs or new dependencies are required. Detailed rules
and completed verification evidence belong in `docs/BUILD_PLANNING.md`.

Completed: typed bindings, pure planner, file-verification wrapper, CLI, original
synthetic tests, installed-package smoke and documentation. Independent manual review
reported no actionable findings. Fresh real-enabled suites passed 251 tests with one
Windows permission skip on both supported local interpreters; offline suite passed
248 with four explicit skips. No writer was implemented or called.
