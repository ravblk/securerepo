"""
SSE Connection Manager for real-time audit status updates.
Manages in-memory subscriptions using asyncio.Queue.
"""

import asyncio
import json
import logging
from typing import Dict, List, AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)


class SSEManager:
    """Manages SSE subscriptions for audit status updates."""

    def __init__(self):
        # audit_id -> List of asyncio.Queue for subscribers
        self._subscriptions: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, audit_id: str) -> AsyncGenerator[str, None]:
        """
        Subscribe to audit status updates.

        Yields SSE-formatted events continuously.
        """
        queue = asyncio.Queue()

        async with self._lock:
            if audit_id not in self._subscriptions:
                self._subscriptions[audit_id] = []
            self._subscriptions[audit_id].append(queue)
            logger.info(f"Client subscribed to audit {audit_id}")

        try:
            # Send initial status immediately
            yield "event: connected\ndata: {}\n\n"

            # Stream events until audit completes or client disconnects
            from api.config import settings
            heartbeat_interval = settings.sse_heartbeat_interval

            while True:
                try:
                    # Wait for message with heartbeat timeout
                    status_data = await asyncio.wait_for(
                        queue.get(),
                        timeout=heartbeat_interval
                    )

                    # Send status update
                    event_str = f"event: status_update\ndata: {json.dumps(status_data)}\n\n"
                    yield event_str

                    # Disconnect if audit is finalized
                    status = status_data.get('status')
                    if status in ('completed', 'failed', 'all_completed'):
                        logger.info(f"Audit {audit_id} finalized, closing SSE")
                        break

                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': datetime.utcnow().isoformat()})}\n\n"

                except asyncio.CancelledError:
                    logger.info(f"Client disconnected from audit {audit_id}")
                    break

        finally:
            # Cleanup subscription
            await self._unsubscribe(audit_id, queue)

    async def broadcast(self, audit_id: str, status_data: dict) -> int:
        """
        Broadcast status update to all subscribers.

        Returns number of subscribers notified.
        """
        async with self._lock:
            if audit_id not in self._subscriptions:
                return 0

            queues = self._subscriptions[audit_id].copy()

        # Send to all queues outside lock to prevent deadlock
        notified = 0
        for queue in queues:
            try:
                await queue.put(status_data)
                notified += 1
            except Exception as e:
                logger.error(f"Failed to send to queue: {e}")

        if notified > 0:
            logger.info(f"Broadcast update to {notified} subscribers of audit {audit_id}")
        return notified

    async def _unsubscribe(self, audit_id: str, queue: asyncio.Queue):
        """Remove queue from subscriptions."""
        async with self._lock:
            if audit_id in self._subscriptions:
                if queue in self._subscriptions[audit_id]:
                    self._subscriptions[audit_id].remove(queue)

                # Clean up empty subscription lists
                if not self._subscriptions[audit_id]:
                    del self._subscriptions[audit_id]

        logger.info(f"Client unsubscribed from audit {audit_id}")

    async def cleanup_inactive_subscriptions(self):
        """Cleanup inactive subscriptions (periodic task)."""
        async with self._lock:
            for audit_id, queues in list(self._subscriptions.items()):
                # Remove subscribers with closed/empty queues
                active_queues = []
                for queue in queues:
                    try:
                        # Test if queue is still active by checking if it's full
                        # This is a simple heuristic - we can't directly check if queue is closed
                        queue.put_nowait({'_cleanup_test': True})
                        # If successful, check if it was meant for us
                        try:
                            msg = queue.get_nowait()
                            if msg.get('_cleanup_test'):
                                # Queue is active, remove our test message
                                active_queues.append(queue)
                        except asyncio.QueueEmpty:
                            pass
                    except (asyncio.QueueFull, asyncio.InvalidStateError):
                        # Queue is full or closed - consider it inactive
                        pass

                if active_queues:
                    self._subscriptions[audit_id] = active_queues
                else:
                    del self._subscriptions[audit_id]

        logger.debug("Cleaned up inactive SSE subscriptions")

    async def get_stats(self) -> dict:
        """Get SSE subscription statistics."""
        async with self._lock:
            total_audits = len(self._subscriptions)
            total_subscribers = sum(len(queues) for queues in self._subscriptions.values())

        return {
            "active_audits": total_audits,
            "total_subscribers": total_subscribers
        }


# Global singleton instance
sse_manager = SSEManager()
