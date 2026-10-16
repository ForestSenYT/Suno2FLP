"""Exact-profile eligibility and immutable-by-reconstruction edit intent; no I/O."""

import hashlib
from fractions import Fraction

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_models import TemplateBindingDocument
from suno2flp.core.errors import FlpWriteError
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.fl26_fields import note_attribute_form
from suno2flp.core.models import Arrangement, Diagnostic
from suno2flp.core.writer_models import Fl26WriteIntent, WriterPolicyDocument
from suno2flp.flp_builder.assessment import assess_template

WRITER_EVENTS = {
    0,
    12,
    17,
    18,
    21,
    64,
    65,
    128,
    135,
    156,
    172,
    192,
    193,
    194,
    195,
    196,
    199,
    201,
    203,
    206,
    207,
    212,
    213,
    224,
    233,
}
METADATA_EVENTS = {
    "track_name",
    "instrument_name",
    "text",
    "copyright",
    "marker",
    "cue_marker",
    "lyrics",
    "end_of_track",
    "set_tempo",
    "time_signature",
    "key_signature",
    "sequence_number",
}


def prepare_fl26_write(
    raw: bytes,
    arrangement: Arrangement,
    inspection: TemplateInspectionReport,
    bindings: TemplateBindingDocument,
    policy: WriterPolicyDocument,
) -> Fl26WriteIntent:
    arrangement = Arrangement.model_validate(arrangement.model_dump())
    bindings = TemplateBindingDocument.model_validate(bindings.model_dump())
    policy = WriterPolicyDocument.model_validate(policy.model_dump())
    assessed = assess_template(raw, inspection, arrangement, bindings)
    inspection, check = assessed.inspection, assessed.binding_check
    assert check is not None and inspection.inventory is not None
    inventory = inspection.inventory
    diagnostics = [d.model_copy(deep=True) for d in check.diagnostics]

    def error(code: str, message: str, event_index: int | None = None) -> None:
        diagnostics.append(
            Diagnostic(code=code, severity="error", message=message, event_index=event_index)
        )

    config = policy.config
    if arrangement.build_options is None or arrangement.build_options.ppq_rounding != "error":
        error(
            "writer_source_rounding",
            "Previously rounded/rounding-enabled arrangements cannot enter the exact writer",
        )
    if config.reference_kind == "unverified" or any(
        review != "attested"
        for review in (config.dependency_review, config.instrument_review, config.local_use_review)
    ):
        error(
            "writer_review_unverified",
            "Dependency/instrument/use and reference evidence remain unverified",
        )
    if (
        config.template_sha256 != inventory.template_sha256
        or config.inventory_snapshot_sha256 != snapshot_sha256(inventory)
        or config.bindings_snapshot_sha256 != snapshot_sha256(bindings.config)
    ):
        error("writer_policy_stale", "Policy must pin the exact template, inventory and bindings")
    if inspection.backend_summary_status != "consistent":
        error(
            "writer_backend_inconsistent",
            "Incomplete/inconsistent backend evidence remains unresolved",
        )
    if inventory.coverage != "decoded":
        error(
            "writer_inventory_incomplete", "Partial/unsupported inventories cannot authorize writes"
        )
    versions = [e for e in inventory.events if e.event_id == 199]
    if (
        len(versions) != 1
        or raw[versions[0].payload_offset : versions[0].payload_offset + versions[0].payload_size]
        != b"26.1.7.5654\0"
    ):
        error("writer_version_bytes", "Writer requires the exact assessed version payload bytes")
    if len({c.pattern_base for c in inventory.clips}) != 1:
        error("writer_clip_base", "Mixed/absent playlist encoding bases remain unsupported")
    for event in inventory.events:
        if event.event_id not in WRITER_EVENTS:
            error(
                "writer_event_unsupported",
                f"Event {event.event_id} is outside the restricted writer allowlist",
                event.event_index,
            )
    if inventory.automation:
        error("writer_automation", "Automation cannot be edited, cleared or inferred safe")
    meter = [e for e in inventory.events if e.event_id in {17, 18}]
    if (
        len(meter) != 2
        or {e.event_id for e in meter} != {17, 18}
        or any(e.scalar_hex != "04" for e in meter)
    ):
        error("writer_template_meter", "Explicit, unique template 4/4 fields required")
    if len(arrangement.meter_map) != 1 or any(
        (m.numerator, m.denominator, m.clocks_per_click, m.notated_32nd_notes_per_beat)
        != (4, 4, 24, 8)
        for m in arrangement.meter_map
    ):
        error("writer_meter", "Only constant default 4/4 is supported")
    tempo = None
    if len(arrangement.tempo_map) != 1:
        error("writer_tempo_map", "Only one effective constant tempo is supported")
    else:
        value = Fraction(60_000_000_000, arrangement.tempo_map[0].microseconds_per_beat)
        if value.denominator != 1 or not 0 < value <= 999000:
            error(
                "writer_tempo_precision", "Tempo must fit exact integer milli-BPM without rounding"
            )
        else:
            tempo = value.numerator
    for source in arrangement.sources:
        for track in source.midi.tracks:
            for source_event in track.events:
                if source_event.message.get("type") not in METADATA_EVENTS | {
                    "note_on",
                    "note_off",
                }:
                    diagnostics.append(
                        Diagnostic(
                            code="source_event_unsupported",
                            severity="error",
                            message="Writer cannot translate this source event",
                            source_input=source.input_index,
                            track_index=track.index,
                            event_index=source_event.event_index,
                            path=source.midi.source,
                        )
                    )
    fine = [e for e in inventory.events if e.event_id == 156]
    playlists = [e for e in inventory.events if e.event_id == 233]
    if len(fine) != 1 or len(playlists) != 1:
        error(
            "writer_event_ambiguous",
            "Exactly one existing fine-tempo and playlist event are required",
        )
    rules = bindings.config.bindings
    pairs = {(r.template_pattern_id, r.template_channel_id) for r in rules}
    for event in inventory.events:
        if event.event_id == 224 and (
            event.pattern_id not in {r.template_pattern_id for r in rules}
            or event.payload_size == 0
        ):
            error(
                "writer_inherited_content",
                "Unbound/empty note events are outside the replacement policy",
                event.event_index,
            )
    lanes = {(r.template_pattern_id, r.template_playlist_track) for r in rules}
    for note in inventory.notes:
        original = bytes.fromhex(note.raw_hex)
        if (note.pattern_id, note.channel_id) not in pairs:
            error(
                "writer_inherited_content",
                "Unbound template notes cannot be silently retained or removed",
                note.event_index,
            )
        if (
            note.position_ticks < 0
            or note.length_ticks <= 0
            or note.pitch > 127
            or not 1 <= note.velocity <= 127
            or note.pan > 127
        ):
            error(
                "writer_note_range", "Template note range/duration is unresolved", note.event_index
            )
        if (
            note.flags or note.group or any(original[13:16]) or any(original[22:24])
        ) and note_attribute_form(note, inventory.profile_id) != "ordinary":
            error(
                "writer_note_attributes",
                "Only zeroed or exact observed ordinary positive-note attributes may be preserved; "
                "slide and unobserved combinations remain unsupported",
                note.event_index,
            )
    for clip in inventory.clips:
        if clip.kind != "pattern" or (clip.item_id, clip.track) not in lanes:
            error(
                "writer_inherited_content",
                "Unbound/non-Pattern clips have no replacement policy",
                clip.event_index,
            )
        if clip.start_offset.raw_hex != "00000000" or clip.end_offset.raw_hex != "00000000":
            error(
                "writer_crop",
                "Only exact positive-zero crop bits are writable; observed Pattern sentinels/tick "
                "endpoints do not establish safe replacement or resize behavior",
                clip.event_index,
            )
        if (
            clip.flags
            or clip.group
            or clip.muted
            or clip.length_ticks <= 0
            or clip.position_ticks < 0
        ):
            error(
                "writer_clip_attributes",
                "Clip attributes/range are outside the restricted subset",
                clip.event_index,
            )
    reviews = {t.binding_index: t for t in config.targets}
    if set(reviews) != set(range(len(rules))):
        error(
            "writer_prototype_unverified",
            "Each binding requires one exact reviewed note/clip prototype",
        )
    dependency_by_index = {d.event_index: d for d in assessed.dependencies}
    backend_channels = {c["id"]: c for c in inspection.project.channels}
    for index, rule in enumerate(rules):
        review = reviews.get(index)
        if review is None:
            continue
        if review.note_index >= len(inventory.notes) or review.clip_index >= len(inventory.clips):
            error("writer_prototype_unverified", f"Binding {index} prototype indices are absent")
            continue
        note, clip = inventory.notes[review.note_index], inventory.clips[review.clip_index]
        if (
            (note.pattern_id, note.channel_id)
            != (rule.template_pattern_id, rule.template_channel_id)
            or (clip.item_id, clip.track, clip.kind)
            != (rule.template_pattern_id, rule.template_playlist_track, "pattern")
            or hashlib.sha256(bytes.fromhex(note.raw_hex)).hexdigest() != review.note_sha256
            or hashlib.sha256(bytes.fromhex(clip.raw_hex)).hexdigest() != review.clip_sha256
        ):
            error("writer_prototype_unverified", f"Binding {index} reviewed raw records differ")
        state = [
            e
            for e in inventory.events
            if e.event_id == 0 and e.channel_id == rule.template_channel_id
        ]
        types = [
            e
            for e in inventory.events
            if e.event_id == 21 and e.channel_id == rule.template_channel_id
        ]
        if (
            len(state) != 1
            or state[0].scalar_hex != "01"
            or len(types) != 1
            or types[0].scalar_hex != "02"
        ):
            error(
                "writer_channel_unverified",
                f"Binding {index} requires explicit enabled generator-channel evidence",
            )
        declaration = dependency_by_index.get(review.generator_event_index)
        backend = backend_channels.get(rule.template_channel_id, {})
        if (
            declaration is None
            or declaration.kind != "generator_declaration"
            or declaration.channel_context != rule.template_channel_id
            or declaration.text_status != "decoded"
            or declaration.text != review.generator_name
            or backend.get("generator") != review.generator_name
            or backend.get("isLikelySequenced") is not False
        ):
            error(
                "writer_generator_unverified",
                f"Binding {index} lacks the reviewed explicit generator declaration",
            )
    changes = sorted({e.event_index for e in inventory.events if e.event_id in {156, 224, 233}})
    inputs = {
        "arrangement": arrangement,
        "inspection": inspection,
        "bindings": bindings,
        "policy": policy,
    }
    return Fl26WriteIntent(
        status="blocked" if any(d.severity == "error" for d in diagnostics) else "ready",
        reference_kind=config.reference_kind,
        arrangement=arrangement,
        inspection=inspection,
        bindings=bindings,
        policy=policy,
        binding_check=check,
        tempo_millibpm=tempo,
        edit_event_indices=changes,
        diagnostics=diagnostics,
        inputs_snapshot_sha256={k: snapshot_sha256(v) for k, v in inputs.items()},
    )


def validate_write_intent(raw: bytes, intent: Fl26WriteIntent) -> Fl26WriteIntent:
    fresh = prepare_fl26_write(
        raw, intent.arrangement, intent.inspection, intent.bindings, intent.policy
    )
    if fresh.model_dump() != intent.model_dump():
        raise FlpWriteError(
            "writer_intent_invalid", "Recorded intent differs from current reconstruction"
        )
    if fresh.status != "ready":
        raise FlpWriteError(
            "writer_blocked", "; ".join(d.code for d in fresh.diagnostics if d.severity == "error")
        )
    return fresh
