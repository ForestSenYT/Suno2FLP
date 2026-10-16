# Local FL Studio templates

No FLP template is shipped. In Phase 3, use an original, licensed template and record
its FL Studio version, required plugins/versions, channel IDs, and SHA-256 hash.
Store it outside generated output/intermediate directories. Builders must create
a distinct output, preserve the source hash, reopen the result, and require a real
FL Studio compatibility/listening check. Never save over the template.

FLP files are ignored by default. See the LFS recommendations before intentionally
versioning any binary template; plugin presets and samples need separate rights.

The [Phase 3 assessment](../docs/FLP_BACKEND_ASSESSMENT.md) found no user template
and could not verify template compatibility at that time. A pinned read-only inspector
is now [available explicitly](../docs/TEMPLATE_INSPECTION.md), and a private user-created
FL26 template has [read-only declaration/readiness evidence](../docs/FL26_READINESS.md).
For an actual host compatibility evaluation,
supply a local template reference and a companion inventory containing:

- Owner/source, permitted local use and separate redistribution permission; no ownership
  or sample/preset rights are inferred from file possession.
- SHA-256, size, FL Studio save build/edition, platform, PPQ, constant meter and tempo;
  note any tempo/meter automation, time markers, controllers or muted content.
- Actual rack-channel/generator, pattern and playlist IDs with enough existing structures
  for the intended arrangement; names and instrument-role hints are not destination IDs.
- Plugin name, format, version, preset/state hashes, required edition/license and samples
  with their resolved paths, hashes and rights. Prefer an original minimal template with
  dependencies the operator owns; avoid third-party preset internals in public metadata.
- All inherited notes, playlist clips/crop offsets, automation and mixer routing to retain
  or explicitly replace in a later experiment; read-only inspection changes none of them.

Keep template references private unless distribution rights are explicit. The recommended
Music2DAW pin requires existing note/playlist events; an arbitrary empty FLP is not yet
an approved template. Record what was actually parsed and distinguish missing evidence
from a successful check. A later copied-output experiment must preserve the template
hash and verify unknown/plugin payloads, exact timing and real FL Studio playback.

Read-only [inventories](../docs/TEMPLATE_INVENTORY.md) now collect known note/clip,
automation and crop records automatically. They supplement the companion manifest;
opaque plugin/track semantics, ownership and playback still need separate evidence.
V2 planning blocks unsupported inventory and inherited-content conflicts without
clearing, merging or writing any template data.
