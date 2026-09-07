"""
TTS In-Memory and Persistent Deduplication Cache.
Prevents duplicate synthesis of identical or normalized speech phrases,
saving cost and reducing latency to 0ms for previously synthesized or standard responses.
"""
import hashlib
import os
import re
from typing import Optional, Dict
from app.core.logging import get_logger

logger = get_logger("tts.cache")


class TTSCacheManager:
    """
    Manages in-memory and disk caching of synthesized PCM16 audio chunks.
    Uses SHA-256 over normalized text + language code as the unique cache key.
    """
    _memory_cache: Dict[str, bytes] = {}
    _max_entries: int = 500
    _disk_cache_dir: Optional[str] = "data/tts_cache"

    @classmethod
    def initialize(cls, disk_cache_dir: Optional[str] = "data/tts_cache", max_entries: int = 500):
        cls._disk_cache_dir = disk_cache_dir
        cls._max_entries = max_entries
        if cls._disk_cache_dir:
            try:
                os.makedirs(cls._disk_cache_dir, exist_ok=True)
            except Exception as e:
                logger.warning(f"Could not create TTS disk cache directory: {e}")

    @classmethod
    def normalize_text_for_cache(cls, text: str) -> str:
        """
        Normalize text to maximize cache hits:
        - Lowercase
        - Collapse multiple spaces
        - Strip leading/trailing whitespace and redundant punctuation
        """
        t = text.strip()
        # Remove markdown formatting if any sneaked through
        t = re.sub(r'[*_~`#>]', '', t)
        t = re.sub(r'\s+', ' ', t)
        return t.strip()

    @classmethod
    def compute_cache_key(cls, text: str, language_code: str, speaker: str = "pooja") -> str:
        """Compute deterministic SHA256 hex digest for normalized text + language + speaker."""
        norm = cls.normalize_text_for_cache(text)
        raw = f"{language_code}:{speaker}:{norm}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def get(cls, text: str, language_code: str, speaker: str = "pooja") -> Optional[bytes]:
        """Retrieve cached PCM bytes if present in RAM or on disk."""
        key = cls.compute_cache_key(text, language_code, speaker)
        
        # 1. Check RAM
        if key in cls._memory_cache:
            pcm = cls._memory_cache[key]
            logger.info(f"[TTS_DEDUP_HIT] Memory cache hit key={key[:10]}... text='{text[:40]}...' ({len(pcm)} bytes)")
            return pcm

        # 2. Check Disk
        if cls._disk_cache_dir:
            path = os.path.join(cls._disk_cache_dir, f"{key}.pcm")
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        pcm = f.read()
                    if pcm and len(pcm) > 0:
                        # Promote to RAM
                        cls._memory_cache[key] = pcm
                        logger.info(f"[TTS_DEDUP_HIT] Disk cache hit key={key[:10]}... text='{text[:40]}...' ({len(pcm)} bytes)")
                        return pcm
                except Exception as e:
                    logger.warning(f"Error reading disk cache for key {key}: {e}")

        logger.info(f"[TTS_DEDUP_MISS] key={key[:10]}... text='{text[:40]}...'")
        return None

    @classmethod
    def put(cls, text: str, language_code: str, pcm: bytes, speaker: str = "pooja") -> None:
        """Store synthesized PCM bytes in RAM and disk cache."""
        if not pcm or len(pcm) == 0:
            return
        key = cls.compute_cache_key(text, language_code, speaker)
        
        # Enforce LRU / size bound on RAM cache
        if len(cls._memory_cache) >= cls._max_entries:
            # Drop oldest entry
            oldest_key = next(iter(cls._memory_cache))
            cls._memory_cache.pop(oldest_key, None)

        cls._memory_cache[key] = pcm

        # Write to disk
        if cls._disk_cache_dir:
            try:
                path = os.path.join(cls._disk_cache_dir, f"{key}.pcm")
                with open(path, "wb") as f:
                    f.write(pcm)
            except Exception as e:
                logger.debug(f"Failed to persist TTS cache to disk: {e}")

    @classmethod
    def clear(cls):
        cls._memory_cache.clear()
