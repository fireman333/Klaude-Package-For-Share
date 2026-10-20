#!/usr/bin/env python3
"""
Biostats Guardian — Pydantic models for Issue / RoleReport / GuardianReport.

Used by runner.py to validate subagent JSON output before writing to disk.
Mirrors schemas/biostats-guardian.schema.json.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field, ValidationError, field_validator
    PYDANTIC_V2 = True
except ImportError:  # pragma: no cover
    try:
        from pydantic.v1 import BaseModel, Field, ValidationError, validator as field_validator
        PYDANTIC_V2 = False
    except ImportError:
        raise ImportError("pydantic is required. Install with: pip install pydantic>=2")


class Role(str, Enum):
    COLUMN = "column"
    CODE = "code"
    RESULTS = "results"


class Severity(str, Enum):
    BLOCK = "block"
    WARN = "warn"
    PASS = "pass"
    UNCERTAIN = "uncertain"


class RoleReportStatus(str, Enum):
    """bg-B-3 audit fix (2026-05-08): enum-enforce status field.

    Previously RoleReport.status was free-form `str` so a subagent returning
    `status="timeout"` with no issues silently passed validation and didn't
    contribute to aggregated_status=error.
    """
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    ERROR = "error"
    SKIPPED = "skipped"


class EvidenceType(str, Enum):
    """bg-D-1 audit fix (2026-05-08): enum-enforce Evidence.type to match
    schemas/biostats-guardian.schema.json. Added `cross_lang_repro` for
    RES-014 cause-specific Cox cross-language sanity check (was used in
    references/results-audit.md but missing from schema).
    """
    CONFIG_FILE = "config_file"
    SCRIPT_FILE = "script_file"
    DATA_FILE = "data_file"
    DATA_DICTIONARY = "data_dictionary"
    RESEARCH_PLAN = "research_plan"
    STDOUT = "stdout"
    STDERR = "stderr"
    OUTPUT_TABLE = "output_table"
    LOG = "log"
    CROSS_LANG_REPRO = "cross_lang_repro"  # P-7 audit: cause-specific Cox R↔Py


class Evidence(BaseModel):
    type: EvidenceType
    pointer: str
    excerpt: Optional[str] = None
    value: Optional[Any] = None


class Issue(BaseModel):
    role: Role
    skill: str
    step_id: Optional[str] = None
    check_id: str
    severity: Severity
    message: str
    evidence: list[Evidence]
    suggestion: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("check_id")
    @classmethod
    def _check_id_pattern(cls, v: str) -> str:
        import re

        if not re.fullmatch(r"(COL|CODE|RES)-\d{3}", v):
            raise ValueError(f"check_id must match ^(COL|CODE|RES)-\\d{{3}}$; got {v!r}")
        return v

    @field_validator("evidence")
    @classmethod
    def _evidence_min_length(cls, v: list[Evidence], info) -> list[Evidence]:
        """bg-R2-3 audit fix (2026-05-08): non-pass issues must have evidence.

        Previously Issue.evidence had no minimum length, so issues without
        any supporting evidence (pointer/excerpt/value) were silently accepted.
        Now: severity != pass requires at least 1 Evidence entry.
        """
        # Pydantic v2: get severity from info.data; v1 fallback uses `values` arg
        try:
            data = info.data if hasattr(info, "data") else {}
        except Exception:
            data = {}
        sev = data.get("severity")
        if sev is not None and sev != Severity.PASS and len(v) == 0:
            raise ValueError(
                "Issue.evidence must contain at least 1 entry when severity != 'pass'"
            )
        return v


class RoleReport(BaseModel):
    role: Role
    skill: str
    step_id: Optional[str] = None
    status: RoleReportStatus  # bg-B-3 fix: was str, now enum
    issues: list[Issue] = Field(default_factory=list)
    summary: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: str
    duration_seconds: Optional[float] = None


class GuardianReport(BaseModel):
    phase: str  # pre|post|ad-hoc
    mode: str  # off|quick|standard|full
    plan_path: Optional[str] = None
    role_reports: list[RoleReport]
    aggregated_status: str  # pass|warn|block|error
    issue_count: dict[str, int] = Field(default_factory=dict)
    generated_at: str
    version: str = "1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def aggregate(role_reports: list[RoleReport], phase: str, mode: str,
              plan_path: Optional[str] = None) -> GuardianReport:
    """Roll up RoleReports into a GuardianReport with aggregated status and counts."""
    blocks = sum(1 for r in role_reports for i in r.issues if i.severity == Severity.BLOCK)
    warns = sum(1 for r in role_reports for i in r.issues if i.severity == Severity.WARN)
    uncertain = sum(1 for r in role_reports for i in r.issues if i.severity == Severity.UNCERTAIN)
    errors = sum(1 for r in role_reports if r.status == "error")

    if errors:
        agg = "error"
    elif blocks:
        agg = "block"
    elif warns:
        agg = "warn"
    else:
        agg = "pass"

    return GuardianReport(
        phase=phase,
        mode=mode,
        plan_path=plan_path,
        role_reports=role_reports,
        aggregated_status=agg,
        issue_count={"block": blocks, "warn": warns, "uncertain": uncertain},
        generated_at=now_iso(),
    )


def validate_report_dict(data: dict) -> GuardianReport:
    """Parse a dict (e.g. from JSON) into a validated GuardianReport."""
    if PYDANTIC_V2:
        return GuardianReport.model_validate(data)
    return GuardianReport.parse_obj(data)  # type: ignore[attr-defined]


__all__ = [
    "Role",
    "Severity",
    "Evidence",
    "Issue",
    "RoleReport",
    "GuardianReport",
    "aggregate",
    "validate_report_dict",
    "now_iso",
    "ValidationError",
]
