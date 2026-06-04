"""Cost dashboard routes — real spend from Azure Cost Management + audit logs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException

from api.core.auth import get_current_user
from api.core.database import AuditLogRow, get_api_session
from api.core.schemas import CostByModelOut, CostSummaryOut, DailyCostOut

_log = structlog.get_logger("codara.cost")

router = APIRouter(prefix="/admin/cost", tags=["cost"])


def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


def _fetch_azure_cost() -> list[dict]:
    """Fetch cost from Azure Cost Management API for the last 30 days.

    Requires AZURE_SUBSCRIPTION_ID + DefaultAzureCredential (Managed Identity or CLI login).
    Returns list of {date, cost, model} dicts. Falls back to empty list on failure.
    """
    import os

    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    if not subscription_id:
        _log.debug("azure_cost_skip", reason="AZURE_SUBSCRIPTION_ID not set")
        return []

    try:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.costmanagement import CostManagementClient
        from azure.mgmt.costmanagement.models import (
            ExportType,
            QueryAggregation,
            QueryDataset,
            QueryDefinition,
            QueryGrouping,
            QueryTimePeriod,
            TimeframeType,
        )

        credential = DefaultAzureCredential()
        client = CostManagementClient(credential)

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)

        scope = f"/subscriptions/{subscription_id}"

        query = QueryDefinition(
            type=ExportType.ACTUAL_COST,
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(from_property=start, to=end),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                grouping=[QueryGrouping(type="Dimension", name="MeterCategory")],
            ),
        )

        result = client.query.usage(scope=scope, parameters=query)

        rows = []
        if result and result.rows:
            for row in result.rows:
                cost_val = float(row[0]) if row[0] else 0.0
                date_val = str(row[1]) if len(row) > 1 else ""
                meter = str(row[2]) if len(row) > 2 else "Azure OpenAI"
                rows.append({"date": date_val[:10], "cost": cost_val, "model": meter})

        _log.info("azure_cost_fetched", rows=len(rows))
        return rows

    except ImportError:
        _log.debug("azure_cost_skip", reason="azure-mgmt-costmanagement not installed")
        return []
    except Exception as exc:
        _log.warning("azure_cost_error", error=str(exc))
        return []


@router.get("", response_model=CostSummaryOut)
def get_cost_summary(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine

    session = get_api_session(engine)
    try:
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        audit_rows = (
            session.query(AuditLogRow).filter(AuditLogRow.timestamp >= thirty_days_ago).all()
        )

        model_stats: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
        daily_stats: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "calls": 0})

        for row in audit_rows:
            model = row.model or "unknown"
            model_stats[model]["calls"] += 1
            model_stats[model]["cost"] += row.cost or 0.0
            # Estimate tokens from latency (rough: ~50 tokens/100ms for typical calls)
            est_tokens = int((row.latency or 0) * 0.5) * 100
            model_stats[model]["tokens"] += est_tokens

            date_key = row.timestamp[:10] if row.timestamp else "unknown"
            daily_stats[date_key]["cost"] += row.cost or 0.0
            daily_stats[date_key]["calls"] += 1

        # Merge Azure Cost Management data if available
        azure_rows = _fetch_azure_cost()
        for ar in azure_rows:
            model_key = f"Azure ({ar['model']})" if ar.get("model") else "Azure OpenAI"
            model_stats[model_key]["cost"] += ar["cost"]
            model_stats[model_key]["calls"] += 1
            daily_stats[ar["date"]]["cost"] += ar["cost"]
            daily_stats[ar["date"]]["calls"] += 1

        total_cost = sum(m["cost"] for m in model_stats.values())
        total_calls = sum(m["calls"] for m in model_stats.values())
        total_tokens = sum(m["tokens"] for m in model_stats.values())

        by_model = [
            CostByModelOut(model=k, calls=v["calls"], tokens=v["tokens"], cost=round(v["cost"], 4))
            for k, v in sorted(model_stats.items(), key=lambda x: -x[1]["cost"])
        ]

        daily = [
            DailyCostOut(date=k, cost=round(v["cost"], 4), calls=v["calls"])
            for k, v in sorted(daily_stats.items())
        ]

        return CostSummaryOut(
            totalCost=round(total_cost, 4),
            totalCalls=total_calls,
            totalTokens=total_tokens,
            byModel=by_model,
            daily=daily,
        )
    finally:
        session.close()
