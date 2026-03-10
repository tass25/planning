"""Analytics routes — conversion stats over time."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from api.auth import get_current_user
from api.database import get_api_session, ConversionRow
from api.schemas import AnalyticsDataOut, FailureModeOut

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=list[AnalyticsDataOut])
def get_analytics(current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        convs = session.query(ConversionRow).all()
        by_date: dict[str, list[ConversionRow]] = defaultdict(list)
        for c in convs:
            date_str = c.created_at[:10] if c.created_at else "unknown"
            by_date[date_str].append(c)

        result: list[AnalyticsDataOut] = []
        for date, items in sorted(by_date.items()):
            total = len(items)
            successes = sum(1 for i in items if i.status == "completed")
            failures = sum(1 for i in items if i.status == "failed")
            avg_lat = sum(i.duration for i in items if i.duration) / max(total, 1)
            result.append(AnalyticsDataOut(
                date=date,
                conversions=total,
                successRate=round((successes / max(total, 1)) * 100, 1),
                avgLatency=round(avg_lat, 1),
                failures=failures,
            ))
        return result
    finally:
        session.close()


@router.get("/failure-modes", response_model=list[FailureModeOut])
def get_failure_modes(current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        failed = session.query(ConversionRow).filter(ConversionRow.status == "failed").all()
        # Categorise by validation report content
        modes: dict[str, int] = defaultdict(int)
        for c in failed:
            report = c.validation_report or ""
            if "macro" in report.lower():
                modes["Macro complexity"] += 1
            elif "proc" in report.lower():
                modes["Unsupported PROC"] += 1
            elif "type" in report.lower():
                modes["Data type mismatch"] += 1
            elif "dependency" in report.lower() or "dep" in report.lower():
                modes["Missing dependency"] += 1
            else:
                modes["Syntax ambiguity"] += 1

        return [FailureModeOut(name=k, value=v) for k, v in sorted(modes.items(), key=lambda x: -x[1])]
    finally:
        session.close()
