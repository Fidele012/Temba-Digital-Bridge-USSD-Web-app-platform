"""
In-memory event bus for real-time USSD → Provider Dashboard push via SSE.
Keyed by org_key = organization_name.lower().strip().
"""
import asyncio
from collections import defaultdict

_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)


def subscribe(org_key: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _queues[org_key].append(q)
    return q


def unsubscribe(org_key: str, q: asyncio.Queue) -> None:
    try:
        _queues[org_key].remove(q)
    except ValueError:
        pass


async def push(org_name: str, payload: dict) -> None:
    key = org_name.lower().strip()
    for q in list(_queues.get(key, [])):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass
