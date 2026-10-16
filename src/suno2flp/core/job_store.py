"""Hash-linked local event records; hashes are integrity evidence, not signatures."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from suno2flp.core.jobs import ConversionJob, JobEvent
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity


class JobRecord(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["job-event-store-v1"] = "job-event-store-v1"
    job_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$", strict=True)
    output_directory: Path
    event: JobEvent
    previous: FileIdentity | None = None


class StoredJob(Contract):
    record: FileIdentity
    records: list[FileIdentity]
    job: ConversionJob
