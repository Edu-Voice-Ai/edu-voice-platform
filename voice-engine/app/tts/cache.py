"""
TTS In-Memory and Persistent Deduplication Cache.
Prevents duplicate synthesis of identical or normalized speech phrases,
saving cost and reducing latency to 0ms for previously synthesized or standard responses.
"""
import hashlib
import os
import re
from typing import Optional, Dict, Any
from app.core.logging import get_logger

logger = get_logger("tts.cache")


class TTSCacheManager:
    """
    Manages in-memory and disk caching of synthesized PCM16 audio chunks.
    Uses SHA-256 over normalized text + language code as the unique cache key.
    Tracks production hit rates and metrics.
    """
    _memory_cache: Dict[str, bytes] = {}
    _max_entries: int = 500
    _disk_cache_dir: Optional[str] = "data/tts_cache"
    _hits: int = 0
    _misses: int = 0

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
        Normalize text to maximize cache hits across semantically identical answers:
        - Lowercase
        - Normalize abbreviations (e.g., 'B.Tech' -> 'btech', 'C.S.E' -> 'cse')
        - Collapse multiple spaces
        - Strip markdown
        - Normalize trailing sentence punctuation (. ! ? -> .)
        - Normalize commas inside numeric digits: 6,00,000 -> 600000
        """
        t = text.strip().lower()
        # Remove markdown formatting
        t = re.sub(r'[*_~`#>]', '', t)
        # Normalize common degree / exam acronyms
        t = re.sub(r'\bb\s*\.?\s*tech\b', 'btech', t)
        t = re.sub(r'\bc\s*\.?\s*s\s*\.?\s*e\b', 'cse', t)
        t = re.sub(r'\be\s*\.?\s*c\s*\.?\s*e\b', 'ece', t)
        t = re.sub(r'\be\s*\.?\s*a\s*\.?\s*m\s*\.?\s*c\s*\.?\s*e\s*\.?\s*t\b', 'eamcet', t)
        # Normalize commas inside numeric digits: 6,00,000 -> 600000
        t = re.sub(r'(?<=\d),(?=\d)', '', t)
        # Collapse multiple spaces
        t = re.sub(r'\s+', ' ', t).strip()
        # Normalize trailing sentence punctuation to single period
        t = re.sub(r'[!?:;.]+$', '.', t)
        return t

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
            cls._hits += 1
            pcm = cls._memory_cache[key]
            total = cls._hits + cls._misses
            rate = (cls._hits / total * 100.0) if total > 0 else 0.0
            logger.info(f"[TTS_DEDUP_HIT] RAM hit key={key[:10]}... text='{text[:40]}...' ({len(pcm)} bytes, hit_rate={rate:.1f}%)")
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
                        cls._hits += 1
                        total = cls._hits + cls._misses
                        rate = (cls._hits / total * 100.0) if total > 0 else 0.0
                        logger.info(f"[TTS_DEDUP_HIT] Disk hit key={key[:10]}... text='{text[:40]}...' ({len(pcm)} bytes, hit_rate={rate:.1f}%)")
                        return pcm
                except Exception as e:
                    logger.warning(f"Error reading disk cache for key {key}: {e}")

        cls._misses += 1
        total = cls._hits + cls._misses
        rate = (cls._hits / total * 100.0) if total > 0 else 0.0
        logger.info(f"[TTS_DEDUP_MISS] key={key[:10]}... text='{text[:40]}...' (hit_rate={rate:.1f}%)")
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
    def get_stats(cls) -> Dict[str, Any]:
        """Return production cache performance metrics."""
        total = cls._hits + cls._misses
        rate = (cls._hits / total * 100.0) if total > 0 else 0.0
        return {
            "hits": cls._hits,
            "misses": cls._misses,
            "total_requests": total,
            "hit_rate_pct": round(rate, 1),
            "ram_entries": len(cls._memory_cache)
        }

    @classmethod
    def clear(cls):
        cls._memory_cache.clear()
        cls._hits = 0
        cls._misses = 0
