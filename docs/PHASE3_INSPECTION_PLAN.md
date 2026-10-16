# Phase 3 isolated provisioning and read-only inspection plan

Authorized scope: provision Music2DAW commit
`6def9463d6fa8636bbc81010581318a39c47d3c4` outside the Python environment;
inspect templates through the CLI's `inspect` operation only. No writer, export,
launch, plugin loading or MCP connection. Continue the architecture selected in
[the assessment](FLP_BACKEND_ASSESSMENT.md), using test-first implementation.

1. Define versioned provisioning/inspection evidence in `core/backend_models.py`.
   Include full source pin, SDK, resolved packages, file hashes, actual runtime,
   template before/after hash, original backend manifest and explicit unverified
   compatibility. Domain failures carry stable codes.
2. Test and implement `integrations/music2daw_provision.py`: new private directory,
   exact Git fetch/checkout verification, isolated NuGet/.NET state, CLI-only
   restore/publish, generated locks, license references and complete artifact hashes.
   Refuse reuse; failure leaves no successful manifest and preserves diagnostics.
3. Test and implement `integrations/music2daw.py`: verify provisioning record and
   hashes, .NET 10 runtime, readable FLP header, fixed `inspect` arguments, timeout,
   strict JSON essentials, returned path/PPQ and unchanged template/backend hashes.
   Missing prerequisites, backend errors and malformed output fail explicitly.
4. Add explicit `provision-music2daw` and `inspect-template` commands. JSON inspection
   reports use stdout or exclusively created `.json` outputs, distinct from inputs
   and the backend directory. No project defaults auto-enable a backend.
5. Provision the real pin locally; record SDK/package/artifact evidence and exercise
   the real read-only CLI with synthetic input plus invalid-input failures. Synthetic
   fixtures create original temporary inputs only; no FLP output is generated.
6. Run offline unit/CLI tests, opt-in real backend tests, both supported Python
   versions, formatting/lint/type checks, package build and installed CLI smoke.
   Request a fresh read-only review and fix concrete findings with regression tests.
7. Synchronize usage, architecture, dependency/license evidence, roadmap, template
   checklist and remaining compatibility blockers. Do not claim FL Studio playback
   or template ownership from successful parsing.

Review focus: modified backend artifacts; wrong source revision; changed template on
failure; unsafe/existing report destinations; missing runtime; malformed/truncated or
inconsistent backend JSON; accidental non-inspection operations; partial provisioning.

Execution notes and actual verification results are recorded in
`docs/TEMPLATE_INSPECTION.md` when available. No commit, push or system installation
is required for this slice.

Completion: all seven steps were implemented and verified. Both Python versions passed
199 tests with the real backend enabled (one OS privilege skip); default offline runs
skip the two external checks explicitly. Installed-wheel inspection and archive checks
passed. Review regressions for incomplete records, NTFS stream destinations and nested
nonfinite JSON were reproduced and fixed. Detailed evidence is in the linked guide.
