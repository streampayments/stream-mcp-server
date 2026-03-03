"""Stream MCP server — FastMCP application entry-point.

Two modes of operation:

* **Local (stdio)** — ``stream-mcp`` command.  Uses ``STREAM_API_KEY`` env var.
* **Remote (SSE)** — ``stream-mcp-remote`` command.  Each user passes their
  own API key as a ``Bearer`` token; the server is stateless.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastmcp import FastMCP

from stream_mcp.client import StreamClient
from stream_mcp.config import settings
from stream_mcp.tools import register_all_tools

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Create a shared StreamClient when an API key is configured."""
    if settings.stream_api_key:
        client = StreamClient(
            api_key=settings.stream_api_key,
            base_url=settings.stream_base_url,
            timeout=settings.stream_timeout,
            max_retries=settings.stream_max_retries,
        )
        async with client:
            logger.info("StreamClient ready -> %s", settings.stream_base_url)
            yield {"client": client}
        logger.info("StreamClient closed.")
    else:
        logger.info("Remote mode — no STREAM_API_KEY set; users must provide Bearer tokens.")
        yield {}


mcp = FastMCP(
    name="stream-mcp",
    instructions=(
        "MCP server for Stream (streampay.sa) — "
        "payment links, customers, products, coupons, invoices, payments."
    ),
    lifespan=lifespan,
)

register_all_tools(mcp)


# ── CLI entry-points ──────────────────────────────────────────────────

def main() -> None:
    """Local mode — stdio transport."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    mcp.run()


def main_remote() -> None:
    """Remote mode — SSE transport with Bearer-token auth.

    Environment variables:
    * ``HOST`` — bind address (default ``0.0.0.0``)
    * ``PORT`` — bind port   (default ``8000``)

    Clients must connect to: http://<host>:<port>/sse
    """
    import uvicorn
    from stream_mcp.auth import BearerAuthMiddleware

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

    host = os.environ.get("HOST", "0.0.0.0")  # noqa: S104 — intentional for container deployments
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        logger.warning("Invalid PORT value, defaulting to 8000")
        port = 8000

    # SSE transport mounts at /sse — clients must use that path
    app = mcp.http_app(transport="sse")
    app = BearerAuthMiddleware(app)

    logger.info("Starting remote MCP server on %s:%d", host, port)
    logger.info("SSE endpoint -> http://%s:%d/sse", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()