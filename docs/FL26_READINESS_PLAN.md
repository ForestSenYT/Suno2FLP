# FL26 read-only readiness batch

User-authorized goal: finish a reviewable evidence package for exact FL Studio
26.1.7.5654: dependency declarations, unresolved semantics, explicit local binding
checks and a future writer design. Preserve the original FLP and pinned backend.
This batch implements no encoder, copy experiment, plugin loading or FLP output.

## Design and acceptance

Extend the existing inspection flow with `assess-template`, consuming a saved
inspection and verifying current template/backend bytes without invoking a process.
An optional arrangement and binding document must be supplied together. Produce new
JSON only. The report embeds the full inspection, dependency declaration evidence,
findings, permanently blocked writer gates, and optional full binding/source snapshots.

Read only already framed exact-profile event payloads: generator declaration 201,
display text 192/203, sample reference 196 and opaque plugin initialization/state
212/213. Strict UTF-16LE decoding retains invalid/empty/raw text evidence; neither
labels nor file references establish plugin identity/version, installation or rights.
Do not expand environment variables, resolve sample paths, search disks, hash external
files or load anything. Mixer-slot boundaries must prevent stale rack-channel ownership.
Backend/runtime/license/artifact evidence remains in the unmodified inspection snapshot.

Local binding checks compare explicit source selectors with actual retained
Pattern/channel note pairs and playlist lanes; the misleading backend's missing
Patterns must remain missing in its snapshot. Exact PPQ conversion is a preview only.
Preserve original channels, notes/events and timing. Distinguish target-byte matches
from instrument intent, generator support or future writer capability. Zero stored
note lengths, flags, crop bits, eight-byte extensions, opaque events and backend
mismatches remain explicit unresolved evidence, never auto-fixed.

File orchestration rechecks source hash/size/mtime and backend artifacts even on
assessment failure; stale inventories and forged comparison evidence fail explicitly.
JSON destinations are exclusively created outside the backend, with no alternate
streams, existing paths or source overwrite. Older reports require current inventory.

## Execution

Use the existing shared checkout and ignored `.tools/` diagnostics; the repository's
bootstrap is untracked, so do not create a worktree that would omit it or stage user
files. No commits, network access, new dependencies or backend changes are needed.
Implement directly with failing synthetic tests first, then run the complete suites.

- [x] 1. Add failing pure assessment tests for declaration provenance, invalid/empty
  text, repeated states, mixer context, zero lengths/flags/crops/extensions, opaque
  coverage and strict exact-build selection. Implement typed models and pure reader.
- [x] 2. Add failing local binding tests: correct local IDs despite backend omission,
  wrong pairs/lanes, incomplete sources, inexact PPQ, unchanged source channels/timing,
  altered reconstruction/comparison and strict paired arguments. Implement checks.
- [x] 3. Add failing file/CLI tests: current-byte regeneration, source mtime and
  backend integrity, failure rechecks, no process calls, output guards, deterministic
  JSON and report round trips. Implement orchestration and `assess-template`.
- [x] 4. Document dependency limitations, exact-build evidence and a writer design
  with explicit eligibility, exclusive staging, unknown-byte preservation, output
  reparse, sidecar and host/listening acceptance. Update historical roadmap status.
- [x] 5. Run Python 3.11/3.14 suites, offline defaults, Ruff/mypy, package/install smoke
  and a fresh independent read-only review. Validate the private original FLP with
  before/after hashes/mtime/backend fingerprints and save private reports exclusively.

Review focus: stale channel context on mixer plugins; invalid UTF-16; source intent
being mistaken for backend support; partial converted notes; stale/tampered evidence;
sample placeholders accidentally causing external reads; failure paths changing files.

## Progress

Baseline: original SHA-256 and mtime match `.tools/fl26-adaptation-baseline.json`;
all pinned backend artifacts verify. New private baseline saved exclusively at
`.tools/fl26-readiness-baseline.json`. Actual original has four sample references,
FLEX and Emphasizer declarations. The latter occurs after mixer-slot events and must
not be attributed to the last selected rack channel. All observations require
hash-linked evidence in the eventual report; no availability or playback is inferred.

Implemented `assess-template` and pure/core/file modules with 45 original synthetic
cases and one opt-in private integration case. Targeted existing/new suites passed
147 tests after review. Independent review found four P2 evidence boundary issues:
incomplete source hash/pairing, additional mixer boundaries, multiple playlist events
and unchecked snapshot fingerprints. Eight new regression cases failed for those
reasons, then passed after one fix pass. Canonical fingerprints now live in inward
`core/evidence.py`; the old planner import remains a compatible re-export with the
same algorithm. There are no deferred review findings or backend/source changes.

Final suites: Python 3.11/3.14 each 375 passed, one Windows privilege skip;
offline 369 passed, seven explicit skips. Ruff/format and strict mypy (47 source files)
passed. Both archives built; installed CLI verified actual declarations, PATH-free
assessment, deterministic JSON/guards and original synthetic binding start/duration
120/240 -> 24/48 at 480 -> 96 PPQ, keeping source channel 2 and backend omissions.
The primary/probe reports and receipts are private ignored JSON; source hash/mtime,
all backend artifacts and Python dependency files stayed unchanged. No FLP was generated.
