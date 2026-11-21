"""Chart generation service for Olist AI Assistant.

Automatically analyzes query results (columns & rows) and constructs
clean, type-safe ChartConfig objects for frontend Recharts rendering:
- Bar charts for rankings, categories, states, and sellers.
- Line charts for monthly trends, time-series, and growth patterns.
- Pie/Donut charts for closed distributions (payment types, order statuses, shares).
"""

import re
from typing import Any, Dict, List, Optional
from app.schemas.chat import ChartConfig


# Common time-related column names
TIME_COLUMNS = {"month_key", "month", "date", "order_date", "purchase_month", "year_month", "period", "day"}

# Closed categorical distribution columns suitable for Pie/Donut charts
DISTRIBUTION_COLUMNS = {"payment_type", "order_status", "status", "review_score", "delivery_status"}


def detect_and_build_chart(
    columns: Optional[List[str]],
    rows: Optional[List[Dict[str, Any]]],
    user_query: str = "",
    sql_query: Optional[str] = None,
    intent: Optional[str] = None,
) -> Optional[ChartConfig]:
    """Inspect query results and generate an appropriate ChartConfig if suitable.
    Returns None if the dataset is not suitable for charting (e.g. single scalar).
    """
    if not columns or not rows or len(rows) < 2 or len(columns) < 2:
        return None

    # Identify categorical/label column (X-axis) and numeric metrics (Y-axis)
    sample_row = rows[0]
    categorical_cols = []
    numeric_cols = []

    for col in columns:
        val = sample_row.get(col)
        # Check if column is numeric across rows
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            numeric_cols.append(col)
        else:
            # Check string representation
            try:
                # If numeric string, could be numeric
                float(str(val))
                numeric_cols.append(col)
            except (ValueError, TypeError):
                categorical_cols.append(col)

    if not categorical_cols or not numeric_cols:
        return None

    x_key = categorical_cols[0]
    # Primary metric for Y-axis
    y_key = numeric_cols[0]

    # Filter out secondary metadata columns from y_keys if needed
    y_keys = [y_key]
    if len(numeric_cols) > 1 and "percentage" not in numeric_cols[1].lower() and "share" not in numeric_cols[1].lower():
        # Add second metric if it represents a meaningful parallel series (e.g. order_count alongside revenue)
        if len(numeric_cols) == 2 and any(k in numeric_cols[1].lower() for k in ["order", "count", "items", "revenue"]):
            y_keys.append(numeric_cols[1])

    # Determine unit
    unit = None
    y_lower = y_key.lower()
    if any(k in y_lower for k in ["revenue", "price", "freight", "payment_value", "total_val", "gmv", "amount"]):
        unit = "R$"
    elif any(k in y_lower for k in ["pct", "percentage", "rate", "taux", "share"]):
        unit = "%"
    elif any(k in y_lower for k in ["count", "orders", "customers", "sellers", "items", "qty", "commandes"]):
        unit = "units"

    # Analyze data and context to choose Chart Type (line, pie, or bar)
    q_lower = user_query.lower()
    x_lower = x_key.lower()

    # 1. LINE CHART: time-series, monthly, dates
    is_time_series = (
        x_lower in TIME_COLUMNS
        or any(k in q_lower for k in ["month", "trend", "over time", "evolution", "mensuel", "croissance", "par mois", "time series"])
        or (isinstance(sample_row.get(x_key), str) and re.match(r"^\d{4}-\d{2}", str(sample_row.get(x_key))))
    )
    if is_time_series:
        chart_type = "line"
        title = _generate_chart_title(x_key, y_key, "trend", user_query)
        # Sort chronologically if needed
        sorted_rows = sorted(rows, key=lambda r: str(r.get(x_key, "")))
        clean_data = _clean_chart_data(sorted_rows[:24], x_key, y_keys)
        return ChartConfig(
            type=chart_type,
            title=title,
            x_key=x_key,
            y_keys=y_keys,
            data=clean_data,
            x_label=x_key.replace("_", " ").title(),
            y_label=y_key.replace("_", " ").title(),
            unit=unit,
        )

    # 2. PIE CHART: closed distributions (2 to 7 items)
    is_distribution = (
        2 <= len(rows) <= 7
        and (
            x_lower in DISTRIBUTION_COLUMNS
            or any(k in q_lower for k in ["payment type", "payment method", "mode de paiement", "order status", "statut", "distribution", "repartition", "share", "proportion"])
            or "payment" in x_lower
            or "status" in x_lower
        )
    )
    if is_distribution:
        chart_type = "pie"
        title = _generate_chart_title(x_key, y_key, "distribution", user_query)
        clean_data = _clean_chart_data(rows, x_key, [y_key])
        return ChartConfig(
            type=chart_type,
            title=title,
            x_key=x_key,
            y_keys=[y_key],
            data=clean_data,
            x_label=x_key.replace("_", " ").title(),
            y_label=y_key.replace("_", " ").title(),
            unit=unit,
        )

    # 3. BAR CHART: rankings, categories, states, sellers, comparisons
    chart_type = "bar"
    title = _generate_chart_title(x_key, y_key, "ranking", user_query)
    # Cap to top 10 (or 15) for optimal readability
    capped_rows = rows[:12]
    clean_data = _clean_chart_data(capped_rows, x_key, y_keys)

    return ChartConfig(
        type=chart_type,
        title=title,
        x_key=x_key,
        y_keys=y_keys,
        data=clean_data,
        x_label=x_key.replace("_", " ").title(),
        y_label=y_key.replace("_", " ").title(),
        unit=unit,
    )


def _clean_chart_data(
    rows: List[Dict[str, Any]],
    x_key: str,
    y_keys: List[str],
) -> List[Dict[str, Any]]:
    """Format and round data values for Recharts serialization."""
    clean = []
    for r in rows:
        item: Dict[str, Any] = {}
        # X key value
        raw_x = r.get(x_key)
        item[x_key] = str(raw_x).replace("_", " ").title() if raw_x is not None else "-"

        # Numeric Y key values
        for y in y_keys:
            val = r.get(y)
            if val is None:
                item[y] = 0
            elif isinstance(val, float):
                item[y] = round(val, 2)
            elif isinstance(val, int):
                item[y] = val
            else:
                try:
                    item[y] = round(float(val), 2)
                except (ValueError, TypeError):
                    item[y] = 0
        clean.append(item)
    return clean


def _generate_chart_title(x_key: str, y_key: str, chart_style: str, user_query: str) -> str:
    """Generate a clean, user-friendly chart title."""
    x_readable = x_key.replace("_", " ").replace("name", "").strip().title()
    y_readable = y_key.replace("_", " ").title()

    if chart_style == "trend":
        return f"{y_readable} Trend over Time"
    elif chart_style == "distribution":
        return f"{x_readable} Distribution ({y_readable})"
    else:
        return f"{y_readable} by {x_readable}"
