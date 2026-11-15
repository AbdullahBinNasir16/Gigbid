"""Customer support RAG chatbot: core module."""
# uses Celery
# uses Redis


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: Celery, Redis, RAG, LangChain."""
    return {"status": "ok", "project": "support-rag-bot"}
