"""Headless Shopify storefront: core module."""
# uses SWR


def run(config: dict) -> dict:
    """Entry point. Pipeline stages: SWR, Shopify, Next.js."""
    return {"status": "ok", "project": "shopify-headless"}
