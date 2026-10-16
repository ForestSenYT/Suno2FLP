"""Pure selected-event declarations; never resolve paths or inspect installed plugins."""

from typing import Literal, cast

from suno2flp.core.assessment_models import DEPENDENCY_EVENTS, DependencyEvidence
from suno2flp.core.template_inventory import TemplateInventory


def dependency_evidence(raw: bytes, inventory: TemplateInventory) -> list[DependencyEvidence]:
    result = []
    channel = None
    for event in inventory.events:
        if event.event_id == 64:
            channel = event.channel_id
        elif event.event_id in {27, 65, 95, 98, 99, 149, 204, 224, 225, 233, 235, 236}:
            # Inventory's last selected rack channel is not mixer/plugin ownership.
            channel = None
        if event.event_id not in DEPENDENCY_EVENTS:
            continue
        payload = raw[event.payload_offset : event.payload_offset + event.payload_size]
        text = None
        status: Literal["decoded", "empty", "invalid", "not_applicable"] = "not_applicable"
        raw_text = None
        if event.event_id not in {212, 213}:
            raw_text = payload.hex()
            try:
                text = payload.decode("utf-16-le").removesuffix("\0")
                status = "decoded" if text else "empty"
            except UnicodeError:
                status = "invalid"
        result.append(
            DependencyEvidence(
                event_index=event.event_index,
                event_id=event.event_id,
                kind=cast(
                    Literal[
                        "display_name",
                        "sample_reference",
                        "generator_declaration",
                        "plugin_initialization",
                        "plugin_state",
                    ],
                    DEPENDENCY_EVENTS[event.event_id],
                ),
                file_offset=event.payload_offset,
                payload_size=event.payload_size,
                payload_sha256=event.payload_sha256,
                channel_context=channel,
                text=text,
                text_status=status,
                raw_text_hex=raw_text,
            )
        )
    return result
