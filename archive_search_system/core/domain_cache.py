"""
Domain Cache System for Deduplication

Manages 24-hour domain cache to prevent duplicate scraping and classification.
Thread-safe with automatic expiration.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Any
from threading import Lock
from urllib.parse import urlparse


class DomainCache:
    """
    24-hour domain deduplication cache

    Thread-safe cache that tracks domains already processed in the current run.
    Prevents duplicate scraping and classification costs.
    """

    def __init__(self, output_dir: Path, ttl_hours: int = 24):
        """
        Initialize domain cache

        Args:
            output_dir: Output directory for this run
            ttl_hours: Time-to-live for cache entries in hours (default: 24)
        """
        self.output_dir = Path(output_dir)
        self.cache_file = self.output_dir / ".cache_domains_24hr.json"
        self.ttl_hours = ttl_hours
        self.lock = Lock()

        # Cache structure: domain -> {added_at, url, metadata}
        self.cache = {}

        # Load existing cache if present
        self._load()

        # Clean expired entries
        self._clean_expired()

    def add(self, url: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a URL/domain to the cache

        Args:
            url: Full URL to cache
            metadata: Optional metadata to store with the domain

        Returns:
            True if added, False if already in cache
        """
        domain = self._extract_domain(url)

        with self.lock:
            if domain in self.cache:
                return False  # Already in cache

            self.cache[domain] = {
                "added_at": datetime.now().isoformat(),
                "url": url,
                "metadata": metadata or {}
            }

            self._save()
            return True

    def contains(self, url: str) -> bool:
        """
        Check if a URL/domain is in the cache

        Args:
            url: Full URL to check

        Returns:
            True if domain is in cache and not expired
        """
        domain = self._extract_domain(url)

        with self.lock:
            if domain not in self.cache:
                return False

            # Check if expired
            entry = self.cache[domain]
            added_at = datetime.fromisoformat(entry["added_at"])
            expires_at = added_at + timedelta(hours=self.ttl_hours)

            if datetime.now() > expires_at:
                # Expired, remove and return False
                del self.cache[domain]
                self._save()
                return False

            return True

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get cache entry for a URL/domain

        Args:
            url: Full URL to lookup

        Returns:
            Cache entry dictionary or None if not found/expired
        """
        domain = self._extract_domain(url)

        with self.lock:
            if domain not in self.cache:
                return None

            # Check if expired
            entry = self.cache[domain]
            added_at = datetime.fromisoformat(entry["added_at"])
            expires_at = added_at + timedelta(hours=self.ttl_hours)

            if datetime.now() > expires_at:
                # Expired, remove and return None
                del self.cache[domain]
                self._save()
                return None

            return entry.copy()

    def get_all_domains(self) -> Set[str]:
        """
        Get all cached domains (non-expired)

        Returns:
            Set of domain strings
        """
        with self.lock:
            self._clean_expired()
            return set(self.cache.keys())

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache stats
        """
        with self.lock:
            self._clean_expired()

            total_domains = len(self.cache)
            domains_by_age = {
                "last_1h": 0,
                "last_6h": 0,
                "last_12h": 0,
                "last_24h": 0
            }

            now = datetime.now()

            for domain, entry in self.cache.items():
                added_at = datetime.fromisoformat(entry["added_at"])
                age_hours = (now - added_at).total_seconds() / 3600

                if age_hours <= 1:
                    domains_by_age["last_1h"] += 1
                if age_hours <= 6:
                    domains_by_age["last_6h"] += 1
                if age_hours <= 12:
                    domains_by_age["last_12h"] += 1
                if age_hours <= 24:
                    domains_by_age["last_24h"] += 1

            return {
                "total_domains": total_domains,
                "ttl_hours": self.ttl_hours,
                "domains_by_age": domains_by_age
            }

    def clear(self):
        """Clear all cache entries"""
        with self.lock:
            self.cache = {}
            self._save()

    def _extract_domain(self, url: str) -> str:
        """
        Extract normalized domain from URL

        Args:
            url: Full URL

        Returns:
            Normalized domain (e.g., "example.com")
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            return domain
        except Exception:
            # If parsing fails, use the URL as-is (lowercased)
            return url.lower()

    def _clean_expired(self):
        """Remove expired entries from cache (must be called within lock)"""
        now = datetime.now()
        expired_domains = []

        for domain, entry in self.cache.items():
            added_at = datetime.fromisoformat(entry["added_at"])
            expires_at = added_at + timedelta(hours=self.ttl_hours)

            if now > expires_at:
                expired_domains.append(domain)

        for domain in expired_domains:
            del self.cache[domain]

        if expired_domains:
            self._save()

    def _load(self):
        """Load cache from file (must be called within lock)"""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                self.cache = data.get("cache", {})
                # Note: TTL from file is not used; we use the constructor TTL
        except Exception:
            # If loading fails, start with empty cache
            self.cache = {}

    def _save(self):
        """Save cache to file (must be called within lock)"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        cache_data = {
            "ttl_hours": self.ttl_hours,
            "last_updated": datetime.now().isoformat(),
            "total_domains": len(self.cache),
            "cache": self.cache
        }

        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)


class GlobalDomainCache:
    """
    Global domain cache that persists across runs

    Unlike DomainCache which is per-run, this cache is shared across all runs
    for a client and persists indefinitely (or until manually cleared).

    Useful for long-term deduplication across multiple pipeline runs.
    """

    def __init__(self, cache_dir: Path, client: str):
        """
        Initialize global domain cache

        Args:
            cache_dir: Directory for global cache files
            client: Client name for client-specific cache
        """
        self.cache_dir = Path(cache_dir)
        self.client = client
        self.cache_file = self.cache_dir / f".global_cache_{client}.json"
        self.lock = Lock()

        # Cache structure: domain -> {first_seen, last_seen, run_ids[]}
        self.cache = {}

        # Load existing cache if present
        self._load()

    def add(self, url: str, run_id: str) -> bool:
        """
        Add a URL/domain to the global cache

        Args:
            url: Full URL to cache
            run_id: Run ID that processed this domain

        Returns:
            True if newly added, False if already existed
        """
        domain = self._extract_domain(url)

        with self.lock:
            now = datetime.now().isoformat()

            if domain in self.cache:
                # Update existing entry
                entry = self.cache[domain]
                entry["last_seen"] = now
                if run_id not in entry["run_ids"]:
                    entry["run_ids"].append(run_id)
                self._save()
                return False
            else:
                # New entry
                self.cache[domain] = {
                    "first_seen": now,
                    "last_seen": now,
                    "url": url,
                    "run_ids": [run_id]
                }
                self._save()
                return True

    def contains(self, url: str) -> bool:
        """
        Check if a URL/domain is in the global cache

        Args:
            url: Full URL to check

        Returns:
            True if domain is in cache
        """
        domain = self._extract_domain(url)

        with self.lock:
            return domain in self.cache

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get cache entry for a URL/domain

        Args:
            url: Full URL to lookup

        Returns:
            Cache entry dictionary or None if not found
        """
        domain = self._extract_domain(url)

        with self.lock:
            if domain not in self.cache:
                return None
            return self.cache[domain].copy()

    def _extract_domain(self, url: str) -> str:
        """Extract normalized domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return url.lower()

    def _load(self):
        """Load cache from file"""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                self.cache = data.get("cache", {})
        except Exception:
            self.cache = {}

    def _save(self):
        """Save cache to file"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        cache_data = {
            "client": self.client,
            "last_updated": datetime.now().isoformat(),
            "total_domains": len(self.cache),
            "cache": self.cache
        }

        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
