"""Retail demand forecasting: core module."""
# uses Prophet


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: Prophet, Time Series, LightGBM."""
    return {"status": "ok", "project": "retail-demand-forecast"}
