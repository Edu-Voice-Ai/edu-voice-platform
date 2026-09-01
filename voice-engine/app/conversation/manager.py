"""ConversationManager coordinating prompt assembly, tool execution, language selection, and message history."""
from typing import List, Dict, Any, Optional
from app.session.state import SessionState
from app.rag.base import RAGProvider, RetrievalQuery
from app.tools.base import ToolRegistry, ToolExecutionResult
from app.conversation.prompts import build_admission_system_prompt
from app.conversation.language import (
    LanguageDetector,
    LanguagePreferenceParser,
    INITIAL_ACKNOWLEDGMENT,
    SWITCH_ACKNOWLEDGMENT,
    LANGUAGE_CLARIFICATION_PROMPT
)
from app.core.logging import get_logger

logger = get_logger("conversation.manager")


class ConversationManager:
    """Coordinates turn conversation context, tenant knowledge retrieval, and tool execution."""

    def __init__(
        self,
        rag_provider: Optional[RAGProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
        max_history_turns: int = 10
    ):
        self.rag_provider = rag_provider
        self.tool_registry = tool_registry
        self.max_history_turns = max_history_turns

    def handle_language_selection_or_switch(
        self,
        session: SessionState,
        user_text: str,
        detected_language: Optional[str] = None
    ) -> Optional[str]:
        """
        Evaluates user text for initial language selection, ambiguous greeting, or explicit language switching.
        Returns:
            Optional direct acknowledgment response text if language was set/switched/clarified.
        """
        # 1. Initial selection
        if not session.language_selection_complete:
            selected_lang = LanguagePreferenceParser.parse_language_preference(user_text)
            
            # If no explicit language keyword was mentioned, check ASR detected language or LanguageDetector
            if selected_lang is None:
                if detected_language in ("te-IN", "hi-IN", "en-IN"):
                    selected_lang = detected_language
                else:
                    selected_lang = LanguageDetector.detect_language(user_text) or "en-IN"

            session.preferred_language = selected_lang
            session.language = selected_lang
            session.language_selection_complete = True
            session.conversation_state = "LISTENING"
            logger.info(f"Language preference selected: {selected_lang}", extra={"session_id": session.session_id})
            
            clean = user_text.lower().strip()
            # If the utterance contains a specific institutional fact question, let LLM/FastQueryRouter answer directly!
            is_specific_inquiry = any(q in clean for q in [
                "fee", "fees", "course", "courses", "cse", "csc", "ece", "hostel", "dates", "eligibility", "admission", "admissions",
                "కాలేజ్", "ఫీజు", "ఎప్పుడు", "ఎంత", "కోర్సులు", "కోర్స్", "కోర్సు", "వివరాలు", "డీటెయిల్స్",
                "ఫీస్", "कब", "कितना", "कोर्स"
            ])
            if not is_specific_inquiry:
                return INITIAL_ACKNOWLEDGMENT.get(selected_lang, INITIAL_ACKNOWLEDGMENT["en-IN"])
            return None

        # 2. Subsequent turns: Check for explicit language switch
        switch_lang = LanguagePreferenceParser.detect_language_switch(user_text)
        if switch_lang and switch_lang != session.preferred_language:
            session.preferred_language = switch_lang
            session.language = switch_lang
            logger.info(f"Language switched to: {switch_lang}", extra={"session_id": session.session_id})
            return SWITCH_ACKNOWLEDGMENT.get(switch_lang, SWITCH_ACKNOWLEDGMENT["en-IN"])

        return None

    async def assemble_llm_messages(
        self,
        session: SessionState,
        latest_user_text: str
    ) -> List[Dict[str, Any]]:
        """Construct full prompt messages list including system prompt, verified RAG context, and history."""
        # 1. Manage language selection & state
        if not session.language_selection_complete:
            selected = LanguagePreferenceParser.parse_language_preference(latest_user_text)
            if selected:
                session.preferred_language = selected
                session.language = selected
                session.language_selection_complete = True
                session.conversation_state = "LISTENING"
        else:
            # Check for explicit language switch
            switched = LanguagePreferenceParser.detect_language_switch(latest_user_text)
            if switched:
                session.preferred_language = switched
                session.language = switched

        active_lang = session.preferred_language or session.language or "en-IN"

        # 2. Retrieve verified tenant knowledge if RAG is available
        verified_context = ""
        if self.rag_provider:
            query = RetrievalQuery(
                organization_id=session.organization_id,
                agent_id=session.agent_id,
                query_text=latest_user_text,
                top_k=2
            )
            retrieval_res = await self.rag_provider.retrieve(query)
            if retrieval_res.has_verified_info:
                verified_context = "\n".join(f"- [{item.title}]: {item.content}" for item in retrieval_res.items)

        # 3. Build system message
        system_content = build_admission_system_prompt(
            institution_name=session.institution_name,
            agent_name="Priya",
            language_hint=active_lang,
            preferred_language=active_lang,
            verified_context=verified_context
        )

        messages = [{"role": "system", "content": system_content}]

        # 4. Append recent message history
        history = session.messages[-self.max_history_turns * 2:]
        for m in history:
            messages.append({"role": m["role"], "content": m["content"]})

        # 5. Append current user query if not already the trailing message in history
        if not (history and history[-1].get("role") == "user" and history[-1].get("content") == latest_user_text):
            messages.append({"role": "user", "content": latest_user_text})
        return messages

    async def execute_tool_if_matched(
        self,
        session: SessionState,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Optional[ToolExecutionResult]:
        """Execute tool if registered."""
        if not self.tool_registry:
            return None

        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            logger.warning(f"Requested tool {tool_name} not found in registry")
            return None

        logger.info(f"Executing tool {tool_name} with args {arguments}", extra={"session_id": session.session_id})
        return await tool.execute(
            organization_id=session.organization_id,
            agent_id=session.agent_id,
            **arguments
        )
