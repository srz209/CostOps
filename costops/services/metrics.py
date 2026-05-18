def money(value):
    return f"${value:,.0f}"


def projected_monthly_warehouse_spend(warehouses):
    days = warehouses["date"].nunique()
    if days == 0:
        return 0
    return float(warehouses["cost_usd"].sum() * 30 / days)


def recommendation_summary(recommendations):
    return {
        "monthly_savings": int(recommendations["projected_monthly_savings"].sum()),
        "annual_savings": int(recommendations["projected_annual_savings"].sum()),
        "realized_monthly_savings": int(recommendations["realized_monthly_savings"].sum()),
        "critical_count": int((recommendations["severity"] == "Critical").sum()),
        "recommendation_count": len(recommendations),
    }


def enrich_recommendation_lifecycle(recommendations, as_of_date):
    enriched = recommendations.copy()
    as_of = as_of_date.normalize()
    first_seen = enriched["first_seen_at"].dt.normalize()
    implemented = enriched["implemented_at"].dt.normalize()
    end_date = implemented.fillna(as_of)

    enriched["days_open"] = (end_date - first_seen).dt.days.clip(lower=0)
    enriched["days_lingering"] = (as_of - first_seen).dt.days.clip(lower=0)
    enriched["missed_savings_to_date"] = (
        enriched["projected_daily_savings"] * enriched["days_open"]
    ).round(0).astype(int)
    enriched["days_since_implementation"] = (as_of - implemented).dt.days
    enriched.loc[enriched["implemented_at"].isna(), "days_since_implementation"] = None
    enriched["is_open"] = ~enriched["status"].isin(["Implemented", "Realized", "Rejected"])
    return enriched


def savings_by_period(recommendations, period):
    multipliers = {
        "MTD": 1,
        "QTD": 3,
        "YTD": 5,
        "Since inception": 12,
    }
    multiplier = multipliers.get(period, 1)
    realized = recommendations["realized_monthly_savings"].sum() * multiplier
    projected = recommendations["projected_monthly_savings"].sum() * multiplier
    return int(realized), int(projected)
