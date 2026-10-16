"""Bind every source group without changing any source event or executing routes."""

from pathlib import Path

from suno2flp.core.midi_routing import (
    MidiRouteBinding,
    MidiRoutingConfig,
    MidiRoutingPlan,
    PlannedMidiRoute,
)
from suno2flp.core.offline_files import capture_input, load_unique_json, verify_inputs
from suno2flp.flp_builder.encoding_assessment import assess_encoding_file


def plan_midi_routing_file(performance_file: Path, bindings_file: Path) -> MidiRoutingPlan:
    identity, raw = capture_input(bindings_file)
    config = MidiRoutingConfig.model_validate(load_unique_json(raw))
    assessment = assess_encoding_file(performance_file)
    bindings: dict[tuple[int, int], MidiRouteBinding] = {}
    destinations: set[tuple[int, int]] = set()
    receivers: dict[str, int] = {}
    ports: dict[int, str] = {}
    for binding in config.bindings:
        source = (binding.source_input, binding.source_channel)
        destination = (binding.destination_port, binding.destination_channel)
        if source in bindings:
            raise ValueError(f"Duplicate source binding: {source}")
        if binding.destination_channel != binding.source_channel:
            raise ValueError(f"Source MIDI channel must remain unchanged: {source}")
        if destination in destinations:
            raise ValueError(f"Multiple sources alias one destination: {destination}")
        if ports.setdefault(binding.destination_port, binding.receiver_id) != binding.receiver_id:
            raise ValueError("One port cannot declare multiple receivers")
        if (
            receivers.setdefault(binding.receiver_id, binding.destination_port)
            != binding.destination_port
        ):
            raise ValueError("One receiver cannot declare multiple ports")
        bindings[source] = binding
        destinations.add(destination)
    expected = {(route.source_input, route.source_channel) for route in assessment.routes}
    if set(bindings) != expected:
        raise ValueError(
            f"Source route coverage mismatch: missing={sorted(expected - set(bindings))}; "
            f"extra={sorted(set(bindings) - expected)}"
        )
    report = MidiRoutingPlan(
        bindings_file=identity,
        config=config,
        assessment=assessment,
        routes=[
            PlannedMidiRoute(
                binding=bindings[(route.source_input, route.source_channel)].model_copy(deep=True),
                source=route.model_copy(deep=True),
            )
            for route in assessment.routes
        ],
        input_files=[identity, *assessment.input_files],
        referenced_paths=[identity.path, *assessment.referenced_paths],
    )
    verify_inputs(report.input_files)
    return report


def verify_midi_routing_file(path: Path) -> MidiRoutingPlan:
    identity, raw = capture_input(path)
    saved = MidiRoutingPlan.model_validate(load_unique_json(raw))
    rebuilt = plan_midi_routing_file(
        saved.assessment.performance_file.path, saved.bindings_file.path
    )
    if saved != rebuilt:
        raise ValueError("MIDI routing plan replay mismatch")
    verify_inputs([identity, *rebuilt.input_files])
    return rebuilt
