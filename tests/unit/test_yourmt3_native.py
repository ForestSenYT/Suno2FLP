"""Malformed or incomplete native evidence must never become a qualified result."""

import importlib

import pytest


def api():
    assert importlib.util.find_spec("suno2flp.core.yourmt3_native"), "Missing raw contract"
    return importlib.import_module("suno2flp.core.yourmt3_native")


def raw():
    return dict(
        windows=[
            dict(index=0, start_frame=0, valid_frames=32767, tokens=[339, 1]),
            dict(index=1, start_frame=32767, valid_frames=1, tokens=[339, 1]),
        ],
        notes=[],
        decoded_windows=[{}, {}],
        events=[[], []],
        decode_errors={"Err/Missing prg": 2},
        merge_errors={},
        configuration={},
        versions={},
        seconds=1.0,
        peak_working_set_bytes=1000000,
        peak_commit_bytes=2000000,
    )


def test_complete_tail_and_native_errors_remain_explicitly_unqualified():
    record = api().YourMT3Native.model_validate(raw())
    api().check_yourmt3_native(record, 98304, 48000)
    assert record.decode_errors == {"Err/Missing prg": 2}
    assert record.musical_correctness == "not_assessed"


@pytest.mark.parametrize("mutation", ["tail", "origin", "token", "negative_error", "nan", "memory"])
def test_invalid_native_geometry_tokens_numbers_or_budgets_are_rejected(mutation):
    value = raw()
    if mutation == "tail":
        value["windows"].pop()
    if mutation == "origin":
        value["windows"][1]["start_frame"] = 32768
    if mutation == "token":
        value["windows"][0]["tokens"] = [596]
    if mutation == "negative_error":
        value["decode_errors"] = {"Err/Missing prg": -1}
    if mutation == "nan":
        value["seconds"] = float("nan")
    if mutation == "memory":
        value["peak_commit_bytes"] = 17 * 1024**3
    with pytest.raises(ValueError):
        record = api().YourMT3Native.model_validate(value)
        api().check_yourmt3_native(record, 98304, 48000)
