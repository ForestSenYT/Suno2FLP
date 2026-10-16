"""Read-only consistency checks for operator-authored records, never host proof."""

import hashlib
import json
import stat
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from suno2flp.core.manual_records import (
    HOST_VERSION,
    REQUIRED_EVIDENCE,
    STAGES,
    ManualFile,
    ManualFileCheck,
    ManualProbeRecord,
    ManualRecordManifest,
    ManualRecordReport,
    ManualRecordSummary,
    StageName,
)
from suno2flp.core.models import Diagnostic


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object)


class _Reader:
    def __init__(self, root: Path, report: ManualRecordReport):
        self.root = root.resolve(strict=True)
        self.report = report
        self.snapshots: dict[Path, tuple[bytes, int]] = {}

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self.report.diagnostics.append(
            Diagnostic(
                code=code, severity="error", message=message, path=Path(path) if path else None
            )
        )

    def path(self, relative: str) -> Path:
        path = self.root / relative
        for part in (path, *path.parents):
            if part == self.root:
                break
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked or reparse evidence paths are not accepted")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise ValueError("Evidence must be a regular file within the explicit root")
        return resolved

    def read(self, reference: ManualFile, role: str) -> bytes | None:
        check = ManualFileCheck(role=role, expected=reference)
        self.report.files.append(check)
        try:
            path = self.path(reference.path)
            before = path.stat()
            raw = path.read_bytes()
            after = path.stat()
            check.actual_sha256 = hashlib.sha256(raw).hexdigest()
            check.actual_size_bytes = len(raw)
            check.actual_mtime_ns = after.st_mtime_ns
            errors = []
            if check.actual_sha256 != reference.sha256:
                errors.append("file_hash_mismatch")
            if len(raw) != reference.size_bytes:
                errors.append("file_size_mismatch")
            if reference.mtime_ns is not None and after.st_mtime_ns != reference.mtime_ns:
                errors.append("file_mtime_mismatch")
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                errors.append("input_changed_during_check")
            if path in self.snapshots and self.snapshots[path] != (raw, after.st_mtime_ns):
                errors.append("input_changed_during_check")
            self.snapshots[path] = raw, after.st_mtime_ns
            for code in errors:
                self.error(
                    code, f"{role}: current file differs from pinned identity", reference.path
                )
            check.valid = not errors
            return raw if check.valid else None
        except (OSError, ValueError, RuntimeError) as exc:
            self.error("file_unavailable", f"{role}: {exc}", reference.path)
            return None

    def finish(self) -> None:
        for path, (raw, mtime) in self.snapshots.items():
            try:
                current = self.path(path.relative_to(self.root).as_posix())
                if current.read_bytes() != raw or current.stat().st_mtime_ns != mtime:
                    raise ValueError("Input changed during the check")
            except (OSError, ValueError, RuntimeError) as exc:
                self.error("input_changed_during_check", str(exc), str(path))
                relative = path.relative_to(self.root).as_posix().casefold()
                for checked in self.report.files:
                    if checked.expected.path.casefold() == relative:
                        checked.valid = False


def _check_record(
    record: ManualProbeRecord,
    reader: _Reader,
    reserved: list[ManualFile],
    output_paths: list[Path],
) -> ManualRecordSummary:
    start_errors = len(reader.report.diagnostics)
    counts: Counter[str] = Counter(stage.status for stage in record.stages.values())
    summary = ManualRecordSummary(
        probe=record.probe,
        pending_stages=counts["pending_not_performed"],
        stage_counts=dict(counts),
    )
    executed = any(
        stage.status in {"pass_observed", "fail_observed"} for stage in record.stages.values()
    )
    partial = any(
        stage.status in {"blocked", "skipped"}
        and (stage.performed_at is not None or stage.details is not None or stage.evidence)
        for stage in record.stages.values()
    )
    if (executed or partial) and not (record.operator and record.operator.strip()):
        reader.error("operator_required", f"{record.probe}: executed stages need an operator")
    if (executed and record.actual_version != HOST_VERSION) or (
        record.actual_version is not None and record.actual_version != HOST_VERSION
    ):
        reader.error("host_version_required", f"{record.probe}: exact actual host version required")
    if counts["pending_not_performed"] == 9 and record.actual_version is not None:
        reader.error(
            "pending_has_results", f"{record.probe}: actual host version without execution"
        )
    previous = None
    successful_prefix = True
    for name in STAGES:
        stage = record.stages[name]
        label = f"{record.probe}/{name}"
        for key, evidence_ref in stage.evidence.items():
            reader.read(evidence_ref, f"{label}/{key}")
        if stage.status == "pending_not_performed":
            if (
                stage.performed_at is not None
                or stage.details is not None
                or stage.reason is not None
                or stage.evidence
            ):
                reader.error("pending_has_results", f"{label}: pending stage contains results")
        elif stage.status in {"blocked", "skipped"}:
            if not (stage.reason and stage.reason.strip()):
                reader.error("stage_reason_required", f"{label}: reason required")
            if stage.performed_at is not None or stage.details is not None or stage.evidence:
                if stage.performed_at is None or not (stage.details and stage.details.strip()):
                    reader.error(
                        "stage_observation_required",
                        f"{label}: partial observation needs time/details",
                    )
        else:
            if stage.performed_at is None or not (stage.details and stage.details.strip()):
                reader.error(
                    "stage_observation_required", f"{label}: time and observation required"
                )
            if stage.status == "pass_observed":
                missing = set(REQUIRED_EVIDENCE[name]) - set(stage.evidence)
                if missing:
                    reader.error("stage_evidence_missing", f"{label}: missing {sorted(missing)}")
                if name != "protection" and not successful_prefix:
                    reader.error(
                        "stage_order_invalid", f"{label}: prerequisite stage not successful"
                    )
            elif not stage.evidence:
                reader.error("stage_evidence_missing", f"{label}: failed attempt needs evidence")
        if stage.performed_at is not None:
            if previous is not None and stage.performed_at < previous:
                reader.error("stage_order_invalid", f"{label}: timestamps out of order")
            previous = stage.performed_at
        if stage.status != "pass_observed":
            successful_prefix = False
            summary.next_required_evidence[name] = list(REQUIRED_EVIDENCE[name])

    output_stages: tuple[tuple[Literal["A", "B"], StageName, StageName], ...] = (
        ("A", "save_a", "reopen_a"),
        ("B", "resize_b", "reopen_b"),
    )
    for output, save_stage, reopen_stage in output_stages:
        ref = record.outputs.get(output)
        saved = record.stages[save_stage].status == "pass_observed"
        reopened = record.stages[reopen_stage].status == "pass_observed"
        if saved or reopened:
            if ref is None:
                reader.error(
                    "saved_output_required", f"{record.probe}: saved {output} identity required"
                )
        if ref is not None:
            if Path(ref.path).suffix.lower() != ".flp":
                reader.error("saved_output_required", f"{record.probe}: {output} must be an FLP")
            reader.read(ref, f"{record.probe}/output_{output}")
            if record.stages[save_stage].status == "pending_not_performed":
                reader.error("pending_has_results", f"{record.probe}: output {output} before save")
            try:
                actual = reader.path(ref.path)
                targets = [reader.root / item.path for item in reserved] + output_paths
                if any(p.exists() and actual.samefile(p) for p in targets):
                    reader.error(
                        "output_overlaps_input", f"{record.probe}: {output} aliases an input/output"
                    )
                output_paths.append(actual)
            except (OSError, ValueError, RuntimeError):
                pass  # The file reader already reports unavailable paths.
        audio = record.listening.get(output, "not_listened")
        if reopened and audio != "heard_as_recorded":
            reader.error(
                "listening_required",
                f"{record.probe}: {output} reopen claims success without listening",
            )
        if (
            record.stages[reopen_stage].status == "pending_not_performed"
            and audio != "not_listened"
        ):
            reader.error("pending_has_results", f"{record.probe}: listening result before reopen")
    if len(reader.report.diagnostics) == start_errors:
        if counts["pending_not_performed"] == 9:
            summary.host_status = "pending_not_performed"
        elif counts["pass_observed"] == 9:
            summary.host_status = "reported_complete"
    return summary


def check_manual_records(manifest_file: Path, root: Path) -> ManualRecordReport:
    """Check pinned files and declared completeness; never repair, spawn or write."""
    report = ManualRecordReport()
    reader = _Reader(root, report)
    try:
        relative = manifest_file.absolute().relative_to(reader.root).as_posix()
        relative = ManualFile.portable_relative(relative)
        path = reader.path(relative)
        raw = path.read_bytes()
        report.manifest_sha256 = hashlib.sha256(raw).hexdigest()
        manifest_ref = ManualFile(
            path=relative,
            sha256=report.manifest_sha256,
            size_bytes=len(raw),
            mtime_ns=path.stat().st_mtime_ns,
        )
        reader.read(manifest_ref, "manifest")
        manifest = ManualRecordManifest.model_validate(_json(raw))
    except (OSError, ValueError, RuntimeError, ValidationError) as exc:
        reader.error("manifest_invalid", str(exc))
        return report
    reserved = [manifest_ref, *manifest.protected_files, *manifest.provenance_files]
    reserved.extend(
        ref for entry in manifest.records for ref in (entry.record, entry.form, entry.candidate)
    )
    for ref in [*manifest.protected_files, *manifest.provenance_files]:
        reader.read(ref, "protected_or_provenance")
    output_paths: list[Path] = []
    for entry in manifest.records:
        before = len(report.diagnostics)
        reader.read(entry.form, f"{entry.probe}/form")
        reader.read(entry.candidate, f"{entry.probe}/candidate")
        raw_record = reader.read(entry.record, f"{entry.probe}/record")
        summary = ManualRecordSummary(probe=entry.probe)
        if raw_record is not None:
            try:
                record = ManualProbeRecord.model_validate(_json(raw_record))
                if record.probe != entry.probe:
                    reader.error(
                        "record_probe_mismatch", f"{entry.probe}: record names another probe"
                    )
                else:
                    summary = _check_record(record, reader, reserved, output_paths)
            except (ValueError, ValidationError) as exc:
                reader.error("record_schema_invalid", f"{entry.probe}: {exc}")
        if len(report.diagnostics) != before:
            summary.host_status = "incomplete"
        report.records.append(summary)
    reader.finish()
    report.integrity_valid = not report.diagnostics
    for summary in report.records:
        if any(
            not checked.valid
            and (
                checked.role.startswith(summary.probe + "/")
                or checked.role in {"manifest", "protected_or_provenance"}
            )
            for checked in report.files
        ):
            summary.host_status = "incomplete"
    counts: Counter[str] = Counter()
    for summary in report.records:
        counts.update(summary.stage_counts)
    report.stage_counts = dict(counts)
    report.unknown_stages = 54 - sum(counts.values())
    if report.integrity_valid:
        if all(item.host_status == "pending_not_performed" for item in report.records):
            report.host_status = "pending_not_performed"
        elif all(item.host_status == "reported_complete" for item in report.records):
            report.host_status = "reported_complete"
    return report


def manual_record_summary(report: ManualRecordReport) -> str:
    """Render only checked metadata; never describe a reported claim as host proof."""
    lines = [
        "# FL26 手动记录：离线完整性汇总",
        "",
        f"- 完整性有效：{str(report.integrity_valid).lower()}",
        f"- 声明的宿主状态：`{report.host_status}`",
        f"- 未执行阶段：{report.stage_counts.get('pending_not_performed', 0)} / 54",
        f"- 无法读取/判断的阶段：{report.unknown_stages}",
        f"- 文件核对：{sum(item.valid for item in report.files)} / {len(report.files)} 有效",
        "- 写入资格：**blocked**；execution_allowed=false；宿主兼容性：unverified",
        "",
        "| 副本 | 声明状态 | 未执行阶段 | 后续待补证据槽数 |",
        "| --- | --- | ---: | ---: |",
    ]
    for record in report.records:
        needed = sum(len(values) for values in record.next_required_evidence.values())
        lines.append(
            f"| {record.probe} | {record.host_status} | {record.pending_stages} | {needed} |"
        )
    if report.diagnostics:
        lines.extend(["", "诊断（详细定位见 JSON 报告）：", ""])
        for diagnostic in report.diagnostics:
            lines.append(f"- `{diagnostic.code}`")
    lines.extend(
        [
            "",
            "仅验证清单一致性与填写完整性；不认证截图/操作者声明，不证明宿主或试听通过。",
            "未引用的文件不自动发现；不解析 Markdown 自由文本来推断结果，不解除任何写入门槛。",
            "",
        ]
    )
    return "\n".join(lines)
