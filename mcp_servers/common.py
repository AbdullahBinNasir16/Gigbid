"""Shared MCP server plumbing: bearer auth, PII masking and an append-only audit log."""

from __future__ import annotations

import hmac
import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = Path(os.environ.get("AUDIT_DIR", ROOT / "data" / "processed" / "audit"))

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_HANDLE = re.compile(r"(?i)(telegram|whatsapp|skype|signal)\s*[:@]?\s*@?[\w.+-]+")


def mask_pii(text: str) -> str:
    """Mask emails, phone numbers, card and bank numbers, and messenger handles."""
    text = _EMAIL.sub("[email]", text)
    text = _CARD.sub("[card]", text)
    text = _IBAN.sub("[iban]", text)
    text = _PHONE.sub("[phone]", text)
    return _HANDLE.sub(lambda m: f"{m.group(1)} [handle]", text)


def mask_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, dict):
        return {k: ("[redacted]" if "token" in k.lower() or "secret" in k.lower() else mask_obj(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_obj(v) for v in obj]
    return obj


_lock = threading.Lock()


def audit(server: str, user: str, tool: str, arguments: dict[str, Any], result: Any,
          trace_id: str | None = None, error: str | None = None) -> None:
    """Append one JSON line per tool call. The file is only ever opened in append mode."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    record = {"at": datetime.now(UTC).isoformat(), "server": server, "user": user, "tool": tool,
              "arguments": mask_obj(arguments), "result": mask_obj(_summ(result)),
              "trace_id": trace_id, "error": error}
    with _lock, (AUDIT_DIR / f"{server}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _summ(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    s = json.dumps(result, default=str)
    return result if len(s) < 2000 else s[:2000] + "...[truncated]"


class BearerAuthMiddleware:
    """ASGI middleware: every request except /health needs Authorization: Bearer <token>.

    When the token env var is empty the server refuses to start in production mode and
    allows unauthenticated access only in development (APP_ENV=development).
    """

    def __init__(self, app: Any, token_env: str) -> None:
        self.app = app
        self.token = os.environ.get(token_env, "")
        if not self.token and os.environ.get("APP_ENV", "development") != "development":
            raise RuntimeError(f"{token_env} must be set outside development")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not self.token or scope.get("path") == "/health":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        got = headers.get(b"authorization", b"").decode()
        if not hmac.compare_digest(got, f"Bearer {self.token}"):
            body = b'{"error":"unauthorized"}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def serve_http(mcp: Any, token_env: str, port: int) -> None:
    """Run a FastMCP server over Streamable HTTP behind bearer auth, plus /health."""
    import uvicorn
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    app = mcp.streamable_http_app()
    app.router.routes.append(Route("/health", lambda r: JSONResponse({"status": "ok"})))
    uvicorn.run(BearerAuthMiddleware(app, token_env), host=os.environ.get("HOST", "0.0.0.0"),
                port=port)
