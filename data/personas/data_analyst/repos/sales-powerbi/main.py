"""Sales performance dashboard: core module."""
# uses Power Query


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: Power Query, Power BI, DAX."""
    return {"status": "ok", "project": "sales-powerbi"}
