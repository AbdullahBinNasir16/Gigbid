"""Heroku to AWS migration: core module."""
# uses GitHub Actions


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: GitHub Actions, AWS, Docker."""
    return {"status": "ok", "project": "devops-migration"}
