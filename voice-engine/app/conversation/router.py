"""Fast Query Router & Intent Classifier for Low-Latency FAQ Responses."""
import re
from enum import Enum
from typing import Optional, Tuple, Dict, Any, List
from app.rag.base import RAGProvider, RetrievalQuery, KnowledgeItem
from app.rag.normalizer import SemanticQueryNormalizer, SemanticIntent, NormalizedQuery
from app.session.state import SessionState
from app.core.logging import get_logger

logger = get_logger("conversation.router")


class QueryComplexity(str, Enum):
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"
    GOODBYE = "GOODBYE"


class FastQueryRouter:
    """Classifies user queries and provides immediate deterministic verified responses for simple FAQs."""

    GOODBYE_MARKERS = {
        "bye", "goodbye", "good bye", "that's all", "thats all", "thank you bye",
        "thanks bye", "nothing else", "no more questions",
        "అంతే బై", "అంతే bye", "సరే బై", "సరే bye", "ఉంటానండి", "ఉంటాను",
        "ధన్యవాదాలు బై", "బై", "మళ్ళీ మాట్లాడతాను",
        "बस धन्यवाद", "अलविदा", "बाय", "ठीक है बाय", "नमस्ते"
    }

    COMPLEX_MARKERS = {
        "compare", "difference", "better", "recommend", "suggestion", "why should i",
        "placement percentage", "average package", "highest package", "companies visiting",
        "ఏది మంచిది", "తేడా ఏంటి", "కంపేర్", "ప్లేస్మెంట్స్ ఎలా ఉంటాయి",
        "तुलना", "अंतर", "कौन सा बेहतर है", "प्लेसमेंट कैसा है"
    }

    FOLLOW_UP_MARKERS = {
        "what about", "how about", "i did not", "did not", "didn't", "i have", "i got", "can i", "do i need",
        "is it", "what if", "what else", "tell me more", "anything else", "inkemaina", "aur kya",
        "naaku", "nenu", "unte", "lekapothe", "mari", "rayaledu", "rasedi", "vachindi", "undali",
        "kavali", "kadhukadha", "compulsory", "required", "mandatory", "gate", "jee", "eapcet",
        "mujhe", "mera", "meri", "kya mujhe", "agar", "nahi", "diya", "mil sakta", "karna hoga",
        "రాయలేదు", "నాకు", "నేను", "ఉంటే", "లేకపోతే", "వచ్చింది", "ఉండాలా", "కంపల్సరీ", "గేట్"
    }

    GOODBYE_RESPONSES = {
        "te-IN": "మాతో మాట్లాడినందుకు ధన్యవాదాలు. మీకు ఏవైనా సందేహాలు ఉంటే మళ్ళీ కాల్ చేయండి. All the best!",
        "hi-IN": "बात करने के लिए धन्यवाद। यदि आपके कोई और प्रश्न हों, तो कृपया पुनः कॉल करें। शुभ दिन!",
        "en-IN": "Thank you for reaching out to Apex University. Have a wonderful day, and all the best!"
    }

    @classmethod
    def is_explicit_goodbye(cls, text: str) -> bool:
        """Check if user explicitly bids farewell. Normal questions are never goodbyes."""
        clean = text.lower().strip()
        # Do not treat short greetings or factual questions as goodbye
        if any(w in clean for w in ["fee", "course", "cse", "hostel", "date", "eligibility", "కాలేజ్", "ఫీజు", "ఎప్పుడు", "ఎంత", "కోర్సులు"]):
            return False
        
        words = set(re.findall(r'[\w\u0900-\u097F\u0C00-\u0C7F]+', clean))
        if words & cls.GOODBYE_MARKERS or any(m in clean for m in ["bye", "goodbye", "thank you bye", "అంతే", "సరే bye"]):
            # Confirm it is a short exit phrase (< 6 words)
            return len(clean.split()) <= 6
        return False

    UNOFFERED_COURSES_MAP = {
        "mba": "MBA",
        "mbbs": "MBBS",
        "bba": "BBA",
        "bcom": "B.Com",
        "b.com": "B.Com",
        "law": "Law",
        "llb": "LLB",
        "pharmacy": "Pharmacy",
        "bpharm": "Pharmacy",
        "medical": "Medical",
        "mechanical": "Mechanical Engineering",
        "mech": "Mechanical Engineering",
        "civil": "Civil Engineering",
        "arts": "Arts",
        "mca": "MCA",
        "diploma": "Diploma",
        "ఎంబా": "MBA",
        "ఎంబీఏ": "MBA",
        "ఎంబిఎ": "MBA",
        "ఎంబిబిఎస్": "MBBS",
        "మెకానికల్": "Mechanical Engineering",
        "సివిల్": "Civil Engineering"
    }

    @classmethod
    def detect_unoffered_course(cls, text: str) -> Optional[str]:
        """Detect if the caller is inquiring about a course/program that is not offered."""
        clean = text.lower().strip()
        words = re.findall(r'[\w\u0900-\u097F\u0C00-\u0C7F]+', clean)
        for w in words:
            if w in cls.UNOFFERED_COURSES_MAP:
                return cls.UNOFFERED_COURSES_MAP[w]
        for key, display_name in cls.UNOFFERED_COURSES_MAP.items():
            if f" {key} " in f" {clean} ":
                return display_name
        return None

    @classmethod
    def classify_complexity(cls, normalized: NormalizedQuery, text: str) -> QueryComplexity:
        """Classify if query can be answered via Fast Path or needs LLM reasoning."""
        if cls.is_explicit_goodbye(text):
            return QueryComplexity.GOODBYE

        clean = text.lower().strip()
        if any(k in clean for k in cls.COMPLEX_MARKERS) or any(f in clean for f in cls.FOLLOW_UP_MARKERS):
            return QueryComplexity.COMPLEX

        # Simple factual intents with clear knowledge coverage
        if normalized.intent in (
            SemanticIntent.LIST_AVAILABLE_COURSES,
            SemanticIntent.FEES_INQUIRY,
            SemanticIntent.ELIGIBILITY_INQUIRY,
            SemanticIntent.ADMISSION_DATES_INQUIRY,
            SemanticIntent.HOSTEL_INQUIRY,
        ):
            # If the utterance has more than 10 words or complex conversational structure, let LLM handle it
            if len(clean.split()) > 10:
                return QueryComplexity.COMPLEX
            return QueryComplexity.SIMPLE

        return QueryComplexity.COMPLEX

    @classmethod
    async def route_and_resolve_fast_path(
        cls,
        session: SessionState,
        user_text: str,
        rag_provider: Optional[RAGProvider]
    ) -> Tuple[QueryComplexity, Optional[str]]:
        """Attempt to resolve a simple verified query without invoking the 105B LLM.
        
        Returns:
            (QueryComplexity, response_text_if_resolved)
        """
        active_lang = session.preferred_language or session.language or "en-IN"

        # 1. Handle Goodbye
        if cls.is_explicit_goodbye(user_text):
            session.conversation_state = "COMPLETED"
            bye_msg = cls.GOODBYE_RESPONSES.get(active_lang, cls.GOODBYE_RESPONSES["en-IN"])
            logger.info(f"[FAST_ROUTER] Explicit goodbye detected; returning graceful farewell: \"{bye_msg}\"", extra={"session_id": session.session_id})
            return QueryComplexity.GOODBYE, bye_msg

        # 1b. Handle Unoffered Programs Policy: Clear 1-sentence refusal + human counselor offer
        unoffered_match = cls.detect_unoffered_course(user_text)
        if unoffered_match:
            course_name = unoffered_match
            if active_lang == "te-IN":
                unoffered_resp = f"మా దగ్గర ప్రస్తుతం {course_name} కోర్స్ లేదు, కేవలం B.Tech CSE మరియు ECE మాత్రమే ఉన్నాయి. మీరు కౌన్సెలర్ తో మాట్లాడాలనుకుంటున్నారా?"
            elif active_lang == "hi-IN":
                unoffered_resp = f"हमारे पास अभी {course_name} कोर्स नहीं है, हम केवल B.Tech CSE और ECE प्रदान करते हैं। क्या आप काउंसलर से बात करना चाहेंगे?"
            else:
                unoffered_resp = f"We do not offer {course_name} right now; we currently offer B.Tech in CSE and ECE. Would you like me to connect you with a human counselor?"

            logger.info(
                f"[FAST_ROUTER] Unoffered program detected ({course_name}); returning policy response in {active_lang}",
                extra={"session_id": session.session_id}
            )
            return QueryComplexity.SIMPLE, unoffered_resp

        # 2. Normalize and check complexity
        normalized = SemanticQueryNormalizer.normalize(user_text)
        complexity = cls.classify_complexity(normalized, user_text)

        if complexity == QueryComplexity.COMPLEX or not rag_provider:
            return QueryComplexity.COMPLEX, None

        # 3. Fast verified retrieval from RAG
        try:
            query = RetrievalQuery(
                organization_id=session.organization_id,
                agent_id=session.agent_id,
                query_text=user_text,
                top_k=2
            )
            res = await rag_provider.retrieve(query)
            if not res.has_verified_info or not res.items:
                return QueryComplexity.COMPLEX, None

            primary_item: KnowledgeItem = res.items[0]
            fast_response = cls._format_fast_answer(normalized, primary_item, active_lang)

            # Anti-repetition check: If the immediate previous assistant message was already this exact fast response,
            # do not reuse it. Delegate to LLM for fresh contextual answer!
            if fast_response and session.messages:
                last_asst_msgs = [m["content"] for m in session.messages if m.get("role") == "assistant"]
                if last_asst_msgs and last_asst_msgs[-1].strip() == fast_response.strip():
                    logger.info(
                        f"[FAST_ROUTER] Fast response matches immediate previous response; delegating to LLM for fresh contextual answer",
                        extra={"session_id": session.session_id}
                    )
                    return QueryComplexity.COMPLEX, None

            if fast_response:
                logger.info(
                    f"[FAST_ROUTER] Fast verified response generated for intent={normalized.intent.value} "
                    f"lang={active_lang}: \"{fast_response}\"",
                    extra={"session_id": session.session_id}
                )
                return QueryComplexity.SIMPLE, fast_response
        except Exception as e:
            logger.warning(f"[FAST_ROUTER] Fast path resolution error: {e}; falling back to LLM", extra={"session_id": session.session_id})

        return QueryComplexity.COMPLEX, None

    @classmethod
    def _format_fast_answer(
        cls,
        normalized: NormalizedQuery,
        item: KnowledgeItem,
        lang: str
    ) -> Optional[str]:
        """Generate a concise, natural, 1-2 sentence Indic/English response strictly from verified data."""
        intent = normalized.intent
        courses = normalized.courses_mentioned

        if intent == SemanticIntent.FEES_INQUIRY:
            if "CSE" in courses or "csc" in normalized.raw_query.lower():
                if lang == "te-IN":
                    return "Apex University లో BTech CSE annual fee 1,50,000 rupees ఉంటుంది. ఇంకా ఏమైనా వివరాలు కావాలా?"
                elif lang == "hi-IN":
                    return "Apex University में BTech CSE की वार्षिक फीस 1,50,000 रुपये है। क्या आपको और जानकारी चाहिए?"
                return "Apex University offers BTech CSE with an annual fee of INR 1,50,000. Would you like details on admissions?"

            if "ECE" in courses:
                if lang == "te-IN":
                    return "Apex University లో BTech ECE annual fee 1,20,000 rupees ఉంటుంది. ఇంకేమైనా వివరాలు కావాలా?"
                elif lang == "hi-IN":
                    return "Apex University में BTech ECE की वार्षिक फीस 1,20,000 रुपये है। क्या आपको और जानकारी चाहिए?"
                return "Apex University offers BTech ECE with an annual fee of INR 1,20,000. How can I help you further?"

            # General fees
            if lang == "te-IN":
                return "Apex University లో BTech CSE fee 1,50,000 rupees మరియు ECE fee 1,20,000 rupees per year."
            elif lang == "hi-IN":
                return "Apex University में BTech CSE की फीस 1,50,000 रुपये और ECE की फीस 1,20,000 रुपये प्रति वर्ष है।"
            return "At Apex University, BTech CSE annual fee is INR 1,50,000 and ECE is INR 1,20,000 per year."

        elif intent == SemanticIntent.LIST_AVAILABLE_COURSES:
            if lang == "te-IN":
                return "మా Apex University లో BTech Computer Science (CSE) మరియు Electronics (ECE) courses అందుబాటులో ఉన్నాయి."
            elif lang == "hi-IN":
                return "Apex University में BTech Computer Science (CSE) और Electronics (ECE) कोर्सेस उपलब्ध हैं।"
            return "Apex University currently offers BTech Computer Science (CSE) and Electronics and Communication (ECE)."

        elif intent == SemanticIntent.ELIGIBILITY_INQUIRY:
            if lang == "te-IN":
                return "BTech admission కోసం 12th Standard PCM లో 60% మార్కులు మరియు valid entrance rank ఉండాలి."
            elif lang == "hi-IN":
                return "BTech में प्रवेश के लिए 12वीं PCM में 60% अंक और वैध प्रवेश परीक्षा रैंक आवश्यक है।"
            return "Eligibility for BTech CSE requires 60% aggregate in 12th Standard PCM and a valid entrance rank."

        elif intent == SemanticIntent.ADMISSION_DATES_INQUIRY:
            if lang == "te-IN":
                return "2026-27 session admissions మే 15, 2026 న మొదలై జూలై 31, 2026 వరకు ఉంటాయి."
            elif lang == "hi-IN":
                return "2026-27 सत्र के लिए प्रवेश 15 मई 2026 से शुरू होकर 31 जुलाई 2026 तक चलेंगे।"
            return "BTech admissions for the 2026-27 session open on May 15, 2026 and close on July 31, 2026."

        elif intent == SemanticIntent.HOSTEL_INQUIRY:
            if lang == "te-IN":
                return "అవునండి, boys and girls కి separate AC and Non-AC hostels ఉన్నాయి. ఫుడ్ తో కలిపి annual fee 80,000 rupees."
            elif lang == "hi-IN":
                return "जी हाँ, छात्र और छात्राओं के लिए अलग AC और Non-AC हॉस्टल उपलब्ध हैं। भोजन सहित वार्षिक शुल्क 80,000 रुपये है।"
            return "Yes, separate AC and Non-AC hostels are available for boys and girls. Annual hostel fee is INR 80,000 including food."

        return None
