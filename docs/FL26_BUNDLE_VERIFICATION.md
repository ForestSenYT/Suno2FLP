# Read-only saved-bundle verification and host acceptance

`verify-flp-bundle` revalidates an existing restricted-writer bundle without encoding,
creating files, launching processes, loading plugins or opening FL Studio. It works on
Windows and Linux; the writer's Windows-only publication restriction is unchanged.

```powershell
uv run suno2flp verify-flp-bundle output/new-build-001 --backend-dir .tools/music2daw-6def9463d6fa-inspect
```

Success returns 0 and prints a freshly derived `Fl26Verification` JSON to stdout,
including output/template hashes, note/clip counts, changed event indices and preserved
event hashes. Its level remains `structural_round_trip_only`, with compatibility
`unverified`. Failure returns 1 with an explicit error. There is no output path, repair,
force, host-launch or offline-trust option.

## Required current evidence

The directory must contain exactly three regular, unchanged files: `project.flp`,
`provenance.json` and `verification.json`. Links, junctions/reparse components, alternate
streams, device names and ambiguous paths are refused by the existing path guard.
The sidecars must retain the canonical JSON bytes produced by the writer. Reformatted
or duplicate-key JSON, disagreement between the two proofs and extra/missing members
fail; a manually edited receipt is not accepted as the original bundle.

Every original arrangement, inspection, binding, policy, source MIDI and template
must still exist at its recorded absolute path, with its recorded hash, size and
modification time. The explicit backend directory must pass the pinned manifest and
artifact checks. A bundle may move to a different directory while those originals
remain available. Relocating original inputs, archiving without them or upgrading the
backend requires a future explicit workflow; this command never silently remaps or
trusts absent evidence.

The verifier reconstructs the intent through the current file preflight, including
MIDI reimport and cleanup replay, local inventory regeneration, exact PPQ and all
writer policy gates. The complete reconstructed intent and ordered input-file records
must equal the retained provenance. Missing/duplicated roles, invented previews,
omitted sources or a forged ready status cannot bypass that reconstruction.

It then runs the independent FL26 output parser against the current original template
and output bytes. Matching hashes in edited receipts do not replace field/count and
untouched-byte checks. The independently derived proof must match both saved proofs.
Finally it rechecks all original/backend fingerprints, bundle bytes/file metadata,
directory identity and file inventory before returning success. Missing or changed
evidence fails even if a prior verification passed. As with the writer, this assumes
a trusted local filesystem; it is not a sandbox against a malicious same-user process.
Receipts are consistency evidence, not signatures or proof of who created a project.

## Remaining real-reference and host gates

The private original `templates/user-minimal.flp` remains blocked. This command takes
a completed bundle, not a template, and does not create a bundle from that original.
Its unresolved zero-length notes, attributes/crops and Music2DAW inventory disagreement
remain unresolved. A passing synthetic bundle cannot close those gaps.

The next required external evidence is a separate, originally authored FL Studio
26.1.7 build 5654 reference whose intended generator, positive piano-roll notes,
playlist placement and inherited attributes are independently known. Create such a
reference as a separate new project/file; preserve the existing private original.
Record the actual host version, note starts/durations/velocities, Pattern/channel/lane
identities, tempo/meter, plugin versions/sample availability and intended local use.
Its inspection must still pass every current compatibility and backend agreement gate;
a new filename or a successful host save does not make a reference eligible.

After an eligible real reference permits a new output, the acceptance order is:

1. Run this read-only command and retain its stdout privately with the output hash.
2. Open only that new output in the intended FL Studio build. Observe warnings and
   missing/changed instruments or samples; independently read back the intended notes,
   tempo/meter and playlist placement, then listen or render for comparison.
3. Record the exact output hash, host version and observations, including failures.
   A save from the host produces different evidence and must use another new filename,
   followed by a separate assessment; do not overwrite the verified bundle or original.

No host observations are fabricated or ingested as automatic approval in this slice.
The command does not implement MCP control, audio reconstruction or audible comparison.
Phase 3 real compatibility remains open until independent evidence closes its blockers;
Phase 4 negotiated DAW control remains planned.

## Tests and publication evidence

Original synthetic fixtures cover complete read-only success, exact file inventory,
canonical sidecars, current-input reconstruction, forged output hashes, changed inputs/
backend, timestamp-only changes, moving a bundle, changes during verification and CLI
success/failure. No private project or backend binary is a public test fixture.

The preceding implementation passed all four GitHub Actions jobs on Windows/Ubuntu
and Python 3.11/3.14 for both push and PR events. See
[PR #1](https://github.com/ForestSenYT/Suno2FLP/pull/1). New changes require their own
fresh local and GitHub checks; the older green result does not cover this slice.
