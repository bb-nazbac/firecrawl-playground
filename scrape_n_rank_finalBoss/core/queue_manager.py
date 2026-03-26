"""
Queue Manager for Inter-Stage Communication

Provides a thread-safe queue for passing items between pipeline stages.
Supports deduplication by a configurable key (default: 'domain').
Designed for streaming pipeline architectures where stages overlap in execution.
"""

import queue
import threading
from typing import Optional, List
from urllib.parse import urlparse


class StageQueue:
    """
    Thread-safe queue for passing items between pipeline stages.

    Features:
    - Automatic deduplication by a configurable key field (default: 'domain')
    - Domain normalization (strips www., lowercases)
    - Batch put operations
    - Poison pill support for signaling completion
    - Statistics tracking
    """

    POISON_PILL = "__STAGE_COMPLETE__"

    def __init__(self, dedup_key: str = "domain"):
        """
        Initialize the stage queue.

        Args:
            dedup_key: Dictionary key to use for deduplication (default: 'domain')
        """
        self._queue = queue.Queue()
        self._seen = set()
        self._lock = threading.Lock()
        self._dedup_key = dedup_key
        self.total_added = 0
        self.total_duplicates = 0
        self._complete = False

    def _normalize_key(self, value: str) -> str:
        """
        Normalize a dedup key value for consistent comparison.

        For domain keys, strips www. prefix and lowercases.
        For other keys, just strips and lowercases.

        Args:
            value: Raw key value

        Returns:
            Normalized string for dedup comparison
        """
        if not value:
            return ''

        normalized = str(value).strip().lower()

        # Domain-specific normalization
        if self._dedup_key == 'domain' or self._dedup_key == 'url':
            if normalized.startswith('http://') or normalized.startswith('https://'):
                try:
                    parsed = urlparse(normalized)
                    normalized = parsed.netloc
                except Exception:
                    pass
            if normalized.startswith('www.'):
                normalized = normalized[4:]

        return normalized

    def put(self, item: dict) -> bool:
        """
        Add an item to the queue (deduplicates by the configured key).

        Args:
            item: Dictionary to enqueue

        Returns:
            True if added, False if duplicate
        """
        key_value = item.get(self._dedup_key, '')
        normalized = self._normalize_key(key_value)

        if not normalized:
            # No valid key - add anyway (no dedup possible)
            self._queue.put(item)
            with self._lock:
                self.total_added += 1
            return True

        with self._lock:
            if normalized in self._seen:
                self.total_duplicates += 1
                return False

            self._seen.add(normalized)
            self.total_added += 1

        self._queue.put(item)
        return True

    def get(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Get next item from the queue.

        Returns None on timeout or if the queue has been signaled as complete
        and is empty.

        Args:
            timeout: How long to wait for an item (seconds)

        Returns:
            Next item dict, or None if timeout/complete
        """
        try:
            item = self._queue.get(timeout=timeout)
            if item == self.POISON_PILL:
                # Put it back so other consumers also see it
                self._queue.put(self.POISON_PILL)
                self._complete = True
                return None
            return item
        except queue.Empty:
            return None

    def put_batch(self, items: list) -> int:
        """
        Add multiple items to the queue.

        Args:
            items: List of dicts to enqueue

        Returns:
            Number of items actually added (after dedup)
        """
        added = 0
        for item in items:
            if self.put(item):
                added += 1
        return added

    def signal_complete(self):
        """
        Signal that no more items will be added.
        Consumers will get None after all remaining items are consumed.
        """
        self._queue.put(self.POISON_PILL)

    @property
    def is_complete(self) -> bool:
        """Check if the producer has signaled completion and queue is drained."""
        return self._complete and self._queue.empty()

    def qsize(self) -> int:
        """Get approximate number of items in queue."""
        return self._queue.qsize()

    def get_stats(self) -> dict:
        """Get queue statistics."""
        with self._lock:
            return {
                "total_added": self.total_added,
                "total_duplicates": self.total_duplicates,
                "unique_items": len(self._seen),
                "current_size": self._queue.qsize(),
                "complete": self._complete,
            }

    def drain(self) -> List[dict]:
        """
        Drain all remaining items from the queue.
        Returns a list of all items. Does not block.

        Returns:
            List of all remaining items
        """
        items = []
        while True:
            try:
                item = self._queue.get_nowait()
                if item == self.POISON_PILL:
                    self._complete = True
                    continue
                items.append(item)
            except queue.Empty:
                break
        return items

    def reset(self):
        """Reset the queue to initial state."""
        with self._lock:
            # Drain the internal queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._seen.clear()
            self.total_added = 0
            self.total_duplicates = 0
            self._complete = False
