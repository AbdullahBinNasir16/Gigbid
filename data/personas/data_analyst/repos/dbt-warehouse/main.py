"""Analytics warehouse with dbt: core module."""
# uses Jinja
# uses Fivetran


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: Jinja, Fivetran, dbt, SQL."""
    return {"status": "ok", "project": "dbt-warehouse"}
