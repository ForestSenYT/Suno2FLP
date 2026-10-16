# Isolated FL26 read-only backend adaptation

User scope: resolve demonstrated backend parsing differences, preserve the original
private FLP and old installation, add synthetic tests/documentation, update PR #1 and
provide Chinese instructions for an independent FL Studio reference project.

The exact upstream pin remains 6def9463d6fa8636bbc81010581318a39c47d3c4; no updated
upstream commit exists at verification. Keep default provisioning unchanged. An explicit
FL26 inspection profile builds a separate private installation from that pin, changing
only its parser's exact-build event-172 framing and 88-byte playlist stride selection.
No third-party source/binary/project is committed. Python carries only an original
deterministic adaptation recipe and metadata; generated GPL source/notices stay private.

- [x] Reproduce old runtime failures with original synthetic fixtures, including
  88-byte arrays also divisible by old strides, plus private read-only verification.
- [x] Add source-hash-guarded recipe, explicit adaptation manifest, isolated provision
  option and source/build integrity checks; preserve legacy manifest serialization.
- [x] Restrict adapted inspection to the exact assessed build and valid event framing;
  reject unsupported layouts before process invocation, retain unknown semantic gates.
- [x] Build the separate genuine runtime, compare its real output with local inventory
  and preserve the old inconsistent report/installation. Never edit/export/launch FLP.
- [x] Add offline integrity/prerequisite/serialization tests and actual runtime tests;
  run full Python 3.11/3.14, lint/type, archives and installed CLI checks.
- [x] Add Chinese host-reference steps sourced from Image-Line manuals; update
  architecture/roadmap/risks, independently review and prepare the verified PR update.

Publication gate: push the verified commit to PR #1 and verify its current-head CI
before reporting completion. Remote run evidence belongs in the PR and private receipt.

Verification: 21 new unit cases and five opt-in runtime cases; Python 3.11/3.14 each
passed 487 tests with one explicit skip; offline defaults passed 475 with 13 skips.
Lint/format, strict typing, installed CLI and independent review passed. The installed
genuine adapted backend also produced a ready **synthetic** preflight without encoding;
the real original remained blocked. Old saved bundles and backend remain verifiable.

Selected count/tempo agreement is not complete field or host compatibility. Raw crops,
opaque attributes, dependencies and production intent remain unresolved. The existing
native writer and permanently blocked preview contracts are not widened in this slice.
