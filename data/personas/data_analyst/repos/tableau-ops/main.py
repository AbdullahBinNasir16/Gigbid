"""Operations KPI dashboard in Tableau: core module."""
# uses Tableau Prep


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: Tableau Prep, Tableau, SQL."""
    return {"status": "ok", "project": "tableau-ops"}
