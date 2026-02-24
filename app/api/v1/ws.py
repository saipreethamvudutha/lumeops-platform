"""
WebSocket endpoint for real-time dashboard updates.

Connection flow:
    1. Client connects to  ws://host/api/v1/ws?token=lum_sk_xxx
    2. Server validates the API key (same auth as REST endpoints)
    3. Server subscribes to the tenant's Redis pub/sub channel
    4. Events are forwarded to the client as JSON messages
    5. Client sends periodic "ping" to keep connection alive
    6. On disconnect, Redis subscription is cleaned up

Security:
    - API key is validated on WebSocket handshake (query param, not header,
      because the browser WebSocket API doesn't support custom headers)
    - Each connection is scoped to a single tenant — you can only receive
      events for the tenant associated with your API key
    - Connection is closed immediately if auth fails (code 4001/4003)

Why query param for auth?
    The browser's WebSocket constructor doesn't support custom headers.
    The standard workaround is to pass the token as a query parameter.
    This is safe because:
    - WebSocket connections upgrade from HTTPS, so the token is encrypted
    - The URL is not logged by our middleware (WS upgrade is a single GET)
    - The token is validated server-side before any data flows

Event Types:
    - inference_received: New inference ingested (prediction, PHI stats)
    - alert_created: New alert triggered (outlier, data quality)
    - stats_update: Periodic dashboard stats snapshot
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.core.pubsub import EventSubscriber
from app.core.security import hash_api_key
from app.models.api_key import APIKey
from app.models.tenant import Tenant

logger = get_logger("websocket")
router = APIRouter()

# Maximum concurrent WebSocket connections per tenant
MAX_CONNECTIONS_PER_TENANT = 50

# Track active connections per tenant for rate limiting
_active_connections: dict[str, int] = {}


async def _authenticate_ws(token: str) -> tuple[str, str] | None:
    """
    Validate an API key for WebSocket authentication.

    Returns (tenant_id, tenant_name) if valid, None if invalid.

    Why a separate function instead of reusing get_current_tenant?
        WebSocket auth happens during the handshake, before the
        connection is fully established. FastAPI's Depends() doesn't
        work with WebSocket query params, so we manually validate.
    """
    settings = get_settings()

    if not token.startswith(settings.API_KEY_PREFIX):
        return None

    key_hash = hash_api_key(token)

    async with async_session_factory() as db:
        # Look up API key
        result = await db.execute(
            select(APIKey).where(
                APIKey.key_hash == key_hash,
                APIKey.is_active.is_(True),
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key is None:
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
            return None

        # Check scope — require 'read' scope for WebSocket
        if api_key.scopes and "read" not in api_key.scopes:
            return None

        # Get tenant
        tenant_result = await db.execute(
            select(Tenant).where(
                Tenant.id == api_key.tenant_id,
                Tenant.is_active.is_(True),
            )
        )
        tenant = tenant_result.scalar_one_or_none()

        if tenant is None:
            return None

        return str(tenant.id), tenant.name


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time event stream for authenticated tenants.

    Connect: ws://host/api/v1/ws?token=lum_sk_xxx

    The server sends JSON messages:
        {"type": "inference_received", "data": {...}}
        {"type": "alert_created", "data": {...}}
        {"type": "connected", "data": {"tenant": "...", "message": "..."}}

    The client can send:
        {"type": "ping"}  →  server replies {"type": "pong"}

    Close codes:
        4001 — Missing or invalid token
        4003 — Authentication failed
        4029 — Too many connections for this tenant
    """
    # ── 1. Extract token from query params ───────────────────────
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    # ── 2. Authenticate ──────────────────────────────────────────
    auth_result = await _authenticate_ws(token)

    if auth_result is None:
        await websocket.close(code=4003, reason="Authentication failed")
        return

    tenant_id, tenant_name = auth_result

    # ── 3. Check connection limit ────────────────────────────────
    current = _active_connections.get(tenant_id, 0)
    if current >= MAX_CONNECTIONS_PER_TENANT:
        await websocket.close(
            code=4029,
            reason="Too many concurrent connections",
        )
        return

    # ── 4. Accept connection ─────────────────────────────────────
    await websocket.accept()
    _active_connections[tenant_id] = current + 1

    logger.info(
        "ws_connected",
        tenant_id=tenant_id,
        active_connections=_active_connections[tenant_id],
    )

    # Send welcome message
    await websocket.send_json({
        "type": "connected",
        "data": {
            "tenant": tenant_name,
            "message": "Real-time event stream active",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    })

    # ── 5. Subscribe to tenant's Redis channel ───────────────────
    subscriber = EventSubscriber(tenant_id)
    connected = await subscriber.connect()

    if not connected:
        # Redis unavailable — still keep WS open, just no pub/sub
        await websocket.send_json({
            "type": "warning",
            "data": {
                "message": "Real-time events temporarily unavailable",
            },
        })

    # ── 6. Run two tasks concurrently ────────────────────────────
    #   - Forward Redis pub/sub messages to WebSocket
    #   - Listen for client pings (keepalive)

    async def forward_events():
        """Forward Redis pub/sub events to WebSocket client."""
        if not connected:
            # No Redis — just sleep forever (WS stays open for pings)
            await asyncio.Event().wait()
            return

        async for event in subscriber.listen():
            try:
                await websocket.send_json(event)
            except Exception:
                break

    async def handle_client_messages():
        """Handle incoming messages from WebSocket client (pings)."""
        try:
            while True:
                data = await websocket.receive_json()

                if data.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "data": {
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    })
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        # Run both tasks — when either finishes, the other is cancelled
        done, pending = await asyncio.wait(
            [
                asyncio.create_task(forward_events()),
                asyncio.create_task(handle_client_messages()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel remaining task
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    finally:
        # ── 7. Cleanup ───────────────────────────────────────────
        await subscriber.close()
        _active_connections[tenant_id] = max(
            0, _active_connections.get(tenant_id, 1) - 1
        )

        logger.info(
            "ws_disconnected",
            tenant_id=tenant_id,
            active_connections=_active_connections.get(tenant_id, 0),
        )
