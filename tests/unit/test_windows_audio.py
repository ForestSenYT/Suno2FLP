"""Original hardware-free observations; discovery never certifies a host."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from suno2flp.core.windows_audio import WindowsAudioFacts, assess_windows_audio


def snapshot(*, active=False):
    return dict(
        protocol="windows-render-endpoints-v1",
        started_ns=10,
        finished_ns=20,
        os_version="original synthetic Windows observation",
        endpoints=[dict(id="endpoint-a", state=1 if active else 8)],
        defaults=[
            dict(
                role=i,
                hresult=0 if active else 0x80070490,
                device_id="endpoint-a" if active else None,
            )
            for i in range(3)
        ],
    )


@pytest.mark.parametrize("active,status", [(False, "output_absent"), (True, "output_detected")])
def test_complete_discovery_is_separate_from_host_qualification(active, status):
    result = assess_windows_audio(WindowsAudioFacts.model_validate(snapshot(active=active)))
    assert result.status == status
    assert result.active_count == int(active)
    assert result.host_compatibility == "unverified"
    assert result.execution_allowed is False


def test_active_device_without_default_is_explicitly_distinct():
    raw = snapshot()
    raw["endpoints"][0]["state"] = 1
    assert assess_windows_audio(WindowsAudioFacts.model_validate(raw)).status == "default_absent"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["endpoints"].append(deepcopy(d["endpoints"][0])),
        lambda d: d["defaults"].__setitem__(2, deepcopy(d["defaults"][0])),
        lambda d: d["defaults"].pop(),
        lambda d: d["endpoints"][0].__setitem__("state", True),
        lambda d: d["endpoints"][0].__setitem__("state", 16),
        lambda d: d["defaults"][0].__setitem__("role", False),
        lambda d: d["defaults"][0].__setitem__("hresult", 0x80070005),
        lambda d: d["defaults"][0].__setitem__("device_id", "invented-default"),
        lambda d: d["defaults"][0].__setitem__("hresult", 0),
        lambda d: d.__setitem__("finished_ns", 9),
    ],
)
def test_incomplete_or_inconsistent_discovery_cannot_look_absent(change):
    raw = snapshot()
    change(raw)
    with pytest.raises(ValidationError):
        WindowsAudioFacts.model_validate(raw)


def test_successful_default_must_be_current_active_enumerated_device():
    raw = snapshot(active=True)
    raw["endpoints"][0]["state"] = 4
    with pytest.raises(ValidationError):
        WindowsAudioFacts.model_validate(raw)


def test_mutated_snapshot_is_revalidated_before_assessment():
    facts = WindowsAudioFacts.model_validate(snapshot())
    facts.defaults.pop()
    with pytest.raises(ValidationError):
        assess_windows_audio(facts)
