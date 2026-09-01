"""Conversation management, system prompts, and multilingual handling."""
from app.conversation.prompts import build_admission_system_prompt, ANTI_HALLUCINATION_RULES
from app.conversation.language import LanguageDetector, normalize_multilingual_text
from app.conversation.manager import ConversationManager

__all__ = [
    "build_admission_system_prompt",
    "ANTI_HALLUCINATION_RULES",
    "LanguageDetector",
    "normalize_multilingual_text",
    "ConversationManager",
]
