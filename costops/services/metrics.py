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
        "critical_count": int((recommendations["severity"] == "Critical").sum()),
        "recommendation_count": len(recommendations),
    }
