# Restricted FL26 writer implementation batch

User authorization: implement the exact 26.1.7.5654 restricted writer, exclusive new
outputs and round-trip verification, original synthetic tests and docs. Preserve
`templates/user-minimal.flp` and full provenance. Unresolved compatibility must block.
The previous [writer design](FL26_WRITER_DESIGN.md) supplies the architecture.

## Concrete restricted contract

Implement an original pure encoder, separate from Music2DAW. Old plans/readiness
reports remain non-executable. A new explicit policy document pins template/inventory/
binding hashes, attested dependency/instrument review and exact prototype note/clip
rows. The policy selects replace-all-bound-notes/clips and preserve-reference-attributes/
88-byte-extension verbatim. It cannot authorize unknown events, zero lengths, nonzero/
nonfinite crop bits, flags/groups/extra note attributes, incomplete source provenance,
unsupported controls/maps, disabled/unknown generators or ambiguous inherited content.
Synthetic references are labeled synthetic; operator-host claims are recorded
attestations, not automatic host verification. No bypass or force flag exists.

The writer allowlist is narrower than the reader. Require one FLdt, one fine tempo,
explicit 4/4 evidence, unique bound note events/clip records, known enabled non-automation
channels and explicit nonempty generator declarations. Backend disagreement remains a
blocker; new local facts never overwrite it. Exactly convert source starts/ends/track
ends to template PPQ and reject precision/range loss.

Generate fresh edit intent from current source snapshots/inspection/bindings/policy.
Encoder rederives it before changing bytes. Only selected note/playlist payloads and
the existing fine tempo can change; retain every other event header/payload/order.
An independent strict framing/record verifier checks expected notes/clips/tempo and
unchanged byte regions, not just the encoder's own expected output hash.

File commands `plan-flp-write` and `build-flp` require explicit inputs/backend/policy.
Only eligible builds stage new `project.flp`, `provenance.json` and `verification.json`
in an exclusively created sibling directory. Verify staged and final bytes, hashes,
input snapshots/source/backend invariants. Publish the complete bundle with a
no-replace Windows rename; unsupported platforms fail before staging. Reject existing
paths, alternate streams, unsafe names, links/junctions/reparse parents, protected
trees and destination races. No overwrite, recursive cleanup or upstream invocation.
Failures retain owned staging for inspection and never return successful BuildResult.
Structural success keeps host/playback compatibility unverified.

## Implementation / verification tasks

- [x] Add failing synthetic intent/encoding tests for exact framing, multibyte lengths,
  source-channel/PPQ provenance, changed-event budget, record extension preservation
  and explicit policy snapshots; implement typed contracts and eligibility.
- [x] Add failing output mutation/reparse tests; implement original encoder and an
  independent verifier with exact note/clip counts, fields and untouched bytes.
- [x] Add failing exclusive-output, race, stale source/backend/policy, failure-path,
  process-free and CLI tests; implement guarded Windows bundle publication.
- [x] Add opt-in actual-template blocking verification; never encode the private
  original while unresolved. Verify input SHA/mtime/backend artifacts on all paths.
- [x] Update architecture, roadmap, usage, dependencies/risks and prior design status.
  Run Python 3.11/3.14 plus offline suites, Ruff/mypy, archives/install smoke, independent
  review and final source/backend/dependency fingerprints.

Shared checkout is necessary because all bootstrap code is currently untracked.
No runtime installs, backend patches, DAW/plugin actions or destructive cleanup are
needed. Scratch evidence lives under ignored `.tools/`. The user subsequently also
authorized committing and pushing verified code/tests/docs to ForestSenYT/Suno2FLP;
use a new `codex/` branch after checking the staged inventory for private assets.

Review focus: synthetic attestation mistaken for real compatibility; old blocked plans
promoted into writes; unbound records silently lost; inexact/partial previews; forged
edit intent; stale MIDI/JSON/policy hashes; untouched opaque payload changes; zero crop
bits/88-byte tail inference; output destination races/reparse aliases; failure return
after publication. User source must retain original SHA-256 and mtime.

## Completion evidence

56 original unit cases plus one opt-in actual negative case were added. Full suites
passed 432/1 skip on Python 3.11/3.14, offline 425/8 explicit skips; Ruff and strict
mypy (53 source files) passed. Independent review identified prior PPQ rounding loss
and unbound empty note-event readiness; both received failing regressions and fixes.

The installed wheel used clearly labeled authored inspection/nonexecuting backend
inventory stubs for positive synthetic writes. A genuine pinned backend still misses
88-byte playlist records and was not altered. Actual source eligibility remains
blocked using honest unreviewed policy; no source-derived FLP/staging was produced.
Archive/source/private receipts are ignored and excluded from the public commit.
