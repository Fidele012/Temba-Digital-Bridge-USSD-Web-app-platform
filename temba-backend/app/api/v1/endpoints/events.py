"""
Server-Sent Events endpoint — streams real-time USSD events to the provider dashboard.
GET /events/stream?token=<JWT>

EventSource in the browser cannot send custom headers, so we authenticate via
a query-param token (same JWT format as Authorization: Bearer <token>).
"""
import asyncio
import json
from typing import Annotated, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.provider_utils import get_provider_for_user
from app.core.security import decode_access_token
from app.db.redis import is_token_blacklisted
from app.db.session import get_db
from app.events import subscribe, unsubscribe
from app.models.user import User, UserRole

router = APIRouter(prefix="/events", tags=["events"])


async def _user_from_token(
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        data = decode_access_token(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    jti = data.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    user_id = data.get("sub")
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.get("/stream")
async def sse_stream(
    current_user: Annotated[User, Depends(_user_from_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    if current_user.role != UserRole.PROVIDER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Provider only")

    prov = await get_provider_for_user(current_user, db)
    if not prov:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No provider profile found")

    org_key = prov.organization_name.lower().strip()

    async def event_stream() -> AsyncGenerator[str, None]:
        q = subscribe(org_key)
        try:
            yield 'data: {"type":"connected"}\n\n'
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            unsubscribe(org_key, q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
