"""Subscription churn prediction: core module."""
# uses SHAP


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: SHAP, Machine Learning, XGBoost."""
    return {"status": "ok", "project": "churn-model"}
