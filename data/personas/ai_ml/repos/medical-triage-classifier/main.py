"""Patient message triage classifier: core module."""
# uses Presidio


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: Presidio, NLP, Text Classification."""
    return {"status": "ok", "project": "medical-triage-classifier"}
