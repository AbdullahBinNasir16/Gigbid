"""AI chat widget for a SaaS site: core module."""
# uses Server-Sent Events


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: Server-Sent Events, React, Node.js."""
    return {"status": "ok", "project": "ai-chat-widget"}
