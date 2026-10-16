# Offline manual-record checks: implementation scope

The existing six Markdown forms stay unchanged and private. Add versioned JSON
companions and a hash-pinned set manifest; the operator edits a new run, never an old
record. This is integrity/completeness checking, not host acceptance or writer policy.

1. Author synthetic pending, claimed-complete, corrupt/missing/stale and contradictory
   records first; observe failing tests before adding the checker.
2. Add inward-facing contracts for the fixed six probes, nine checklist stages,
   file identities, declared observations and permanently blocked summaries.
3. Implement process-free file checking and evidence rules. Require explicit operator,
   exact host version, time with timezone, observations and stage-specific evidence
   for reported success. Pending stages must not contain claimed execution evidence;
   blocked/skipped stages need a reason. Check saved A/B identity and input separation.
4. Expose `check-host-records MANIFEST --root ROOT [--output NEW.json]`. Intact pending
   records return 0 while remaining host-unverified; malformed/stale/incomplete claims
   return 1. Only a new JSON report may be written, never FLP or repaired inputs.
5. Prepare six new local JSON companions linked to the existing unchanged forms,
   candidates, source records and protected fingerprints. Produce new JSON/Markdown
   summaries with actual pending states, no backend/DAW invocation or public private data.
6. Document the contract/limits, run offline tests/lint/typing and independent review,
   commit public code/tests/docs only, update PR #1 and verify CI.

File hashes establish consistency with the supplied manifest, not authenticity of
operator claims or screenshots. Evidence-file contents are not interpreted as proof
of GUI geometry, audible behavior or crop/flag semantics. Unknowns remain blocked.
