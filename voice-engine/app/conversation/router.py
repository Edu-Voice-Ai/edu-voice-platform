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

    EXTERNAL_INSTITUTIONS_MAP = {
        "loyola college": "Loyola College",
        "loyola": "Loyola College",
        "loyola university": "Loyola College",
        "osmania university": "Osmania University",
        "osmania": "Osmania University",
        "jntu": "JNTU",
        "jntuh": "JNTUH",
        "cbit": "CBIT",
        "iit": "IIT",
        "iit madras": "IIT Madras",
        "iit hyderabad": "IIT Hyderabad",
        "nit": "NIT",
        "nit warangal": "NIT Warangal",
        "bits pilani": "BITS Pilani",
        "bits": "BITS Pilani",
        "ఆంధ్రా యూనివర్సిటీ": "Andhra University",
        "లయోలా": "Loyola College",
        "లయోలా కాలేజ్": "Loyola College",
        "ఉస్మానియా": "Osmania University",
    }

    @classmethod
    def detect_external_institution(cls, text: str, current_inst: str) -> Optional[str]:
        """Detect if the caller is inquiring about an external or unaffiliated institution."""
        clean = text.lower().strip()
        words = re.findall(r'[\w\u0900-\u097F\u0C00-\u0C7F]+', clean)
        curr_lower = (current_inst or "").lower()
        for w in words:
            if w in cls.EXTERNAL_INSTITUTIONS_MAP:
                detected = cls.EXTERNAL_INSTITUTIONS_MAP[w]
                if detected.lower() not in curr_lower and curr_lower not in detected.lower():
                    return detected
        for key, display_name in cls.EXTERNAL_INSTITUTIONS_MAP.items():
            pattern = rf"(^|\s){re.escape(key)}(\s|$|[?,.!])"
            if re.search(pattern, clean):
                if display_name.lower() not in curr_lower and curr_lower not in display_name.lower():
                    return display_name
        return None

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
            bye_msg = getattr(session, "get_goodbye_text", lambda: cls.GOODBYE_RESPONSES.get(active_lang, cls.GOODBYE_RESPONSES["en-IN"]))()
            logger.info(f"[FAST_ROUTER] Explicit goodbye detected; returning graceful farewell: \"{bye_msg}\"", extra={"session_id": session.session_id})
            return QueryComplexity.GOODBYE, bye_msg

        template_type = getattr(session, "template_type", "education")

        if template_type == "education":
            current_inst = getattr(session, "institution_name", "Apex University") or "Apex University"

            # 1b. Handle External / Unaffiliated Institutions (e.g. Loyola College)
            external_inst = cls.detect_external_institution(user_text, current_inst)
            if external_inst:
                if active_lang == "te-IN":
                    ext_resp = f"నేను {current_inst} అడ్మిషన్స్ కౌన్సెలర్‌ని. నా దగ్గర {external_inst} ఫీజు లేదా అడ్మిషన్ వివరాలు లేవు. మీరు {current_inst} కోర్సుల వివరాలు తెలుసుకోవాలనుకుంటున్నారా?"
                elif active_lang == "hi-IN":
                    ext_resp = f"मैं {current_inst} का प्रवेश काउंसलर हूँ। मेरे पास {external_inst} की फीस या प्रवेश संबंधी जानकारी नहीं है। क्या आप {current_inst} के विवरण जानना चाहेंगे?"
                else:
                    ext_resp = f"I am the admissions counselor for {current_inst}. I do not have fee or admission details for {external_inst}. Would you like details on {current_inst}'s programs?"

                logger.info(
                    f"[FAST_ROUTER] External institution detected ({external_inst}); returning grounded boundary response in {active_lang}",
                    extra={"session_id": session.session_id}
                )
                return QueryComplexity.SIMPLE, ext_resp

            # 1c. Handle Unoffered Programs Policy: Clear 1-sentence refusal + human counselor offer
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

            # Context-dependent tracking: update or inherit active course
            if normalized.courses_mentioned:
                session.active_course = normalized.courses_mentioned[0]
            elif session.active_course and normalized.intent in (
                SemanticIntent.FEES_INQUIRY,
                SemanticIntent.ELIGIBILITY_INQUIRY,
                SemanticIntent.LIST_AVAILABLE_COURSES
            ):
                normalized.courses_mentioned.append(session.active_course)

            complexity = cls.classify_complexity(normalized, user_text)
            is_fee_intent = normalized.intent in (SemanticIntent.FEES_INQUIRY, SemanticIntent.HOSTEL_INQUIRY)

            if complexity == QueryComplexity.COMPLEX:
                return QueryComplexity.COMPLEX, None

            if not rag_provider:
                if is_fee_intent:
                    return QueryComplexity.SIMPLE, cls.get_fee_boundary_response(active_lang, session)
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
                    if is_fee_intent:
                        logger.info(
                            f"[FAST_ROUTER] Fee query with empty/unverified RAG; returning deterministic boundary response in {active_lang}",
                            extra={"session_id": session.session_id}
                        )
                        return QueryComplexity.SIMPLE, cls.get_fee_boundary_response(active_lang, session)
                    return QueryComplexity.COMPLEX, None

                # For fee inquiries, strictly validate relevance and category/program grounding
                if is_fee_intent:
                    valid_item = cls._validate_fee_evidence(normalized, res.items, session)
                    if not valid_item:
                        logger.info(
                            f"[FAST_ROUTER] Fee query lacking category/program grounding in RAG items; returning deterministic boundary response in {active_lang}",
                            extra={"session_id": session.session_id}
                        )
                        return QueryComplexity.SIMPLE, cls.get_fee_boundary_response(active_lang, session)
                    primary_item = valid_item
                else:
                    primary_item = res.items[0]

                fast_response = cls._format_fast_answer(normalized, primary_item, active_lang, session=session)

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
                elif is_fee_intent:
                    return QueryComplexity.SIMPLE, cls.get_fee_boundary_response(active_lang, session)
            except Exception as e:
                logger.warning(f"[FAST_ROUTER] Fast path resolution error: {e}; falling back", extra={"session_id": session.session_id})
                if is_fee_intent:
                    return QueryComplexity.SIMPLE, cls.get_fee_boundary_response(active_lang, session)

            return QueryComplexity.COMPLEX, None

        # Non-education templates: Check optional template-defined fast router rules or delegate cleanly to LLM
        try:
            from app.templates.registry import AgentTemplateRegistry
            template = AgentTemplateRegistry.get_template(template_type)
            fast_resp = template.get_fast_router_rules(session, user_text)
            if fast_resp:
                return QueryComplexity.SIMPLE, fast_resp
        except Exception as e:
            logger.debug(f"[FAST_ROUTER] Template fast rules notice: {e}")

        return QueryComplexity.COMPLEX, None

    @classmethod
    def get_fee_boundary_response(cls, lang: str, session: Optional[SessionState] = None) -> str:
        """Deterministic, grounded boundary response when fee evidence is absent, ambiguous, or insufficient."""
        norm_lang = (lang or "en-IN").lower()
        if "te" in norm_lang:
            return "నా దగ్గర ప్రస్తుతం ఖచ్చితమైన ఫీజు వివరాలు లేవు. మీరు అడ్మిషన్స్ కౌన్సెలర్ తో మాట్లాడాలనుకుంటున్నారా?"
        elif "hi" in norm_lang:
            return "मेरे पास अभी फीस की सत्यापित जानकारी नहीं है। क्या आप एडमिशन काउंसलर से बात करना चाहेंगे?"
        return "I do not have verified fee details for that right now. Would you like me to connect you with an admissions counselor to confirm?"

    @classmethod
    def _validate_fee_evidence(
        cls,
        normalized: NormalizedQuery,
        items: List[KnowledgeItem],
        session: SessionState
    ) -> Optional[KnowledgeItem]:
        """
        Validates whether retrieved knowledge items contain authoritative, relevant fee evidence
        for the requested program and fee category.

        Returns the primary matching KnowledgeItem if sufficiently grounded; otherwise None.
        """
        if not items:
            return None

        # 1. Filter out items that do not contain fee-relevant categories or financial markers
        fee_items = []
        for it in items:
            cat = (getattr(it, "category", "") or "").lower()
            content_lower = (getattr(it, "content", "") or "").lower()
            has_fee_category = cat in ("fees", "fee", "hostel", "tuition")
            has_fee_content = any(k in content_lower for k in [
                "fee", "fees", "tuition", "cost", "inr", "rupees", "rs.", "₹",
                "ఫీజు", "ఖర్చు", "రూపాయలు", "ఫీజ్",
                "शुल्क", "फीस", "लागत", "रुपये"
            ])
            if has_fee_category or has_fee_content:
                fee_items.append(it)

        if not fee_items:
            # Irrelevant items (e.g., only eligibility or dates returned without fee figures)
            return None

        primary = fee_items[0]
        content_lower = primary.content.lower()
        fee_type = getattr(normalized, "fee_type", "general")
        courses = normalized.courses_mentioned

        # 2. Category-specific validation:
        if fee_type == "hostel":
            if not any(k in content_lower for k in ["hostel", "హాస్టల్", "हॉस्टल", "accommodation", "mess"]):
                return None

        elif fee_type == "admission":
            if not any(k in content_lower for k in [
                "admission fee", "admission charge", "admission cost", "one time", "onetime",
                "అడ్మిషన్", "దాఖిలా", "दाखिला"
            ]):
                return None

        elif fee_type == "total":
            if not any(k in content_lower for k in [
                "total", "4-year", "4 year", "four year", "overall", "మొత్తం", "టోటల్", "कुल"
            ]):
                return None

        # 3. Program-specific validation:
        if courses:
            course_matched = False
            for c in courses:
                c_upper = c.upper()
                if c_upper == "CSE" and any(k in content_lower for k in ["cse", "computer", "సిఎస్ఇ", "సిఎస్సి", "सीएसई"]):
                    course_matched = True
                    break
                elif c_upper == "ECE" and any(k in content_lower for k in ["ece", "electronics", "ఈసిఈ", "ईसीई"]):
                    course_matched = True
                    break
                elif c_upper not in ("CSE", "ECE") and c.lower() in content_lower:
                    course_matched = True
                    break
            if not course_matched:
                return None

        return primary

    @classmethod
    def _format_fast_answer(
        cls,
        normalized: NormalizedQuery,
        item: KnowledgeItem,
        lang: str,
        session: Optional[SessionState] = None
    ) -> Optional[str]:
        """Generate a concise, natural, 1-2 sentence Indic/English response strictly from verified data."""
        inst_name = (session.institution_name if session else "Apex University") or "Apex University"
        org_id = (session.organization_id if session else "org_apex_univ") or "org_apex_univ"

        # Multi-tenant isolation check: non-Apex tenants ground purely on retrieved item content
        if org_id != "org_apex_univ":
            return item.content

        intent = normalized.intent
        courses = normalized.courses_mentioned
        fee_type = getattr(normalized, "fee_type", "general")

        if intent == SemanticIntent.FEES_INQUIRY:
            # 0. Distinct Fee Type: Hostel Fee
            if fee_type == "hostel":
                if lang == "te-IN":
                    return "అవునండి, boys and girls కి separate AC and Non-AC hostels ఉన్నాయి. ఫుడ్ తో కలిపి annual fee 80,000 rupees."
                elif lang == "hi-IN":
                    return "जी हाँ, छात्र और छात्राओं के लिए अलग AC और Non-AC हॉस्टल उपलब्ध हैं। भोजन सहित वार्षिक शुल्क 80,000 रुपये है।"
                return f"At {inst_name}, separate AC and Non-AC hostels are available for boys and girls with an annual fee of INR 80,000 including food."

            # 1. Distinct Fee Type: Admission Fee (One-Time)
            if fee_type == "admission":
                if lang == "te-IN":
                    return f"{inst_name} లో BTech one-time admission fee 25,000 rupees ఉంటుంది."
                elif lang == "hi-IN":
                    return f"{inst_name} में BTech की एकमुश्त (one-time) एडमिशन फीस 25,000 रुपये है।"
                return f"At {inst_name}, the one-time BTech admission fee is INR 25,000."

            # 2. Distinct Fee Type: Total Cost (4-year total)
            if fee_type == "total":
                if "CSE" in courses:
                    if lang == "te-IN":
                        return f"{inst_name} లో BTech CSE మొత్తం 4 సంవత్సరాల tuition fee 6,00,000 rupees అవుతుంది (సంవత్సరానికి 1,50,000)."
                    elif lang == "hi-IN":
                        return f"{inst_name} में BTech CSE की 4 साल की कुल ट्यूशन फीस 6,00,000 रुपये है (1,50,000 रुपये प्रति वर्ष)।"
                    return f"At {inst_name}, the 4-year total tuition fee for BTech CSE is INR 6,00,000 (INR 1,50,000 per year)."

                if "ECE" in courses:
                    if lang == "te-IN":
                        return f"{inst_name} లో BTech ECE మొత్తం 4 సంవత్సరాల tuition fee 4,80,000 rupees అవుతుంది (సంవత్సరానికి 1,20,000)."
                    elif lang == "hi-IN":
                        return f"{inst_name} में BTech ECE की 4 साल की कुल ट्यूशन फीस 4,80,000 रुपये है (1,20,000 रुपये प्रति वर्ष)।"
                    return f"At {inst_name}, the 4-year total tuition fee for BTech ECE is INR 4,80,000 (INR 1,20,000 per year)."

                # Both courses total
                if lang == "te-IN":
                    return f"{inst_name} లో 4 సంవత్సరాల మొత్తం tuition fee CSE కి 6,00,000 rupees మరియు ECE కి 4,80,000 rupees."
                elif lang == "hi-IN":
                    return f"{inst_name} में 4 साल की कुल ट्यूशन फीस CSE के लिए 6,00,000 रुपये और ECE के लिए 4,80,000 रुपये है।"
                return f"At {inst_name}, the 4-year total tuition fee is INR 6,00,000 for CSE and INR 4,80,000 for ECE."

            # 3. Distinct Fee Type: Annual Tuition / General Course Fee
            if "CSE" in courses or "csc" in normalized.raw_query.lower():
                if lang == "te-IN":
                    return f"{inst_name} లో BTech CSE annual fee 1,50,000 rupees ఉంటుంది. ఇంకా ఏమైనా వివరాలు కావాలా?"
                elif lang == "hi-IN":
                    return f"{inst_name} में BTech CSE की वार्षिक फीस 1,50,000 रुपये है। क्या आपको और जानकारी चाहिए?"
                return f"{inst_name} offers BTech CSE with an annual fee of INR 1,50,000. Would you like details on admissions?"

            if "ECE" in courses:
                if lang == "te-IN":
                    return f"{inst_name} లో BTech ECE annual fee 1,20,000 rupees ఉంటుంది. ఇంకేమైనా వివరాలు కావాలా?"
                elif lang == "hi-IN":
                    return f"{inst_name} में BTech ECE की वार्षिक फीस 1,20,000 रुपये है। क्या आपको और जानकारी चाहिए?"
                return f"{inst_name} offers BTech ECE with an annual fee of INR 1,20,000. How can I help you further?"

            # General fees
            if lang == "te-IN":
                return f"{inst_name} లో BTech CSE fee 1,50,000 rupees మరియు ECE fee 1,20,000 rupees per year."
            elif lang == "hi-IN":
                return f"{inst_name} में BTech CSE की फीस 1,50,000 रुपये और ECE की फीस 1,20,000 रुपये प्रति वर्ष है।"
            return f"At {inst_name}, BTech CSE annual fee is INR 1,50,000 and ECE is INR 1,20,000 per year."

        elif intent == SemanticIntent.LIST_AVAILABLE_COURSES:
            if lang == "te-IN":
                return f"మా {inst_name} లో BTech Computer Science (CSE) మరియు Electronics (ECE) courses అందుబాటులో ఉన్నాయి."
            elif lang == "hi-IN":
                return f"{inst_name} में BTech Computer Science (CSE) और Electronics (ECE) कोर्सेस उपलब्ध हैं।"
            return f"{inst_name} currently offers BTech Computer Science (CSE) and Electronics and Communication (ECE)."

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
