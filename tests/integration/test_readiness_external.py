"""Explicit opt-in assessment of the same private, user-selected FL26 template."""

import os
from pathlib import Path

import pytest

from suno2flp.core.assessment_models import TemplateReadinessReport
from suno2flp.flp_builder.assessment_files import assess_template_files
from suno2flp.integrations.music2daw import Music2DawInspector
from suno2flp.integrations.music2daw_provision import verify_backend

pytestmark = pytest.mark.external


def test_private_fl26_assessment_retains_dependency_and_blocking_evidence(tmp_path, monkeypatch):
    source = os.environ.get("SUNO2FLP_FL26_TEMPLATE")
    backend = os.environ.get("SUNO2FLP_MUSIC2DAW_DIR")
    if not source or not backend:
        pytest.skip("Set SUNO2FLP_FL26_TEMPLATE and SUNO2FLP_MUSIC2DAW_DIR for private assessment")
    path, directory = Path(source), Path(backend)
    before = path.read_bytes(), path.stat().st_mtime_ns
    backend_before = verify_backend(directory)
    inspection = Music2DawInspector(directory).inspect(path)
    saved = tmp_path / "inspection.json"
    saved.write_text(inspection.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        "subprocess.run", lambda *_a, **_k: pytest.fail("Assessment launched a process")
    )
    result = assess_template_files(saved, directory)
    assert result.inspection == inspection
    assert result.inspection.backend_summary_status == "inconsistent"
    assert result.dependencies and all(d.availability == "unverified" for d in result.dependencies)
    assert result.writer_status == "blocked" and result.execution_allowed is False
    assert result.binding_check is None
    assert TemplateReadinessReport.model_validate_json(result.model_dump_json()) == result
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert verify_backend(directory) == backend_before
