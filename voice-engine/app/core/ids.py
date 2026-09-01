"""ID generation utilities for sessions, turns, generations, and frames."""
import uuid
import time


def generate_id(prefix: str = "id") -> str:
    """Generate a prefixed timestamp-ordered unique identifier."""
    timestamp = int(time.time() * 1000)
    rand_suffix = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{rand_suffix}"


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return generate_id("sess")


def generate_turn_id() -> str:
    """Generate a unique turn ID."""
    return generate_id("turn")


def generate_generation_id() -> str:
    """Generate a unique generation ID for response/audio cycles."""
    return generate_id("gen")
