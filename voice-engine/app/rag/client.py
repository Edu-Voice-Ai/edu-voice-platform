"""Backend RAG HTTP Client and Mock Multi-Tenant RAG Provider."""
from typing import List, Dict, Optional
import httpx
from app.rag.base import RAGProvider, KnowledgeItem, RetrievalQuery, RetrievalResult
from app.core.errors import RAGError
from app.core.logging import get_logger

logger = get_logger("rag.client")


class BackendRAGClient(RAGProvider):
    """Client for querying the FastAPI backend RAG service with tenant verification."""

    def __init__(self, endpoint_url: str = "http://localhost:8000/api/v1/rag", api_key: Optional[str] = None):
        self.endpoint_url = endpoint_url
        self.api_key = api_key

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        if not query.organization_id:
            raise RAGError("organization_id is strictly required for knowledge retrieval")

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    self.endpoint_url,
                    headers=headers,
                    json=query.model_dump()
                )
                if resp.status_code != 200:
                    logger.warning(f"Backend RAG returned {resp.status_code}: {resp.text}")
                    return RetrievalResult(items=[], has_verified_info=False)

                data = resp.json()
                items = [
                    KnowledgeItem(
                        id=d.get("id", ""),
                        organization_id=query.organization_id,
                        agent_id=query.agent_id,
                        title=d.get("title", ""),
                        content=d.get("content", ""),
                        category=d.get("category", "general"),
                        score=float(d.get("score", 1.0))
                    )
                    for d in data.get("items", [])
                ]
                return RetrievalResult(items=items, has_verified_info=len(items) > 0)
        except Exception as e:
            logger.error(f"Failed to reach backend RAG: {e}")
            return RetrievalResult(items=[], has_verified_info=False)


class MockRAGProvider(RAGProvider):
    """Multi-tenant Mock RAG providing deterministic factual data for testing."""

    def __init__(self):
        # Tenant-isolated mock knowledge base
        self._store: Dict[str, List[KnowledgeItem]] = {
            "org_apex_univ": [
                KnowledgeItem(
                    id="kb_1",
                    organization_id="org_apex_univ",
                    agent_id="agent_admission",
                    title="BTech Courses & Fees",
                    content="Apex University offers BTech Computer Science and Engineering (CSE) with an annual fee of INR 1,50,000. BTech Electronics and Communication (ECE) fee is INR 1,20,000. We only offer B.Tech in CSE and ECE. Other programs like MBA, MBBS, BBA, Law are not offered.",
                    category="fees"
                ),
                KnowledgeItem(
                    id="kb_unoffered",
                    organization_id="org_apex_univ",
                    agent_id="agent_admission",
                    title="Unoffered Programs Policy",
                    content="Apex University only offers B.Tech in CSE and ECE. Courses like MBA, MBBS, BBA, B.Com, Pharmacy, Law, Mechanical, Civil, Arts are not offered. When asked, state clearly we do not offer that course right now, currently only offer B.Tech in CSE and ECE, and offer to connect with a human counselor.",
                    category="courses"
                ),
                KnowledgeItem(
                    id="kb_2",
                    organization_id="org_apex_univ",
                    agent_id="agent_admission",
                    title="Eligibility Criteria",
                    content="Eligibility for BTech CSE: 60% aggregate in 12th Standard PCM and valid state/JEE entrance rank.",
                    category="eligibility"
                ),
                KnowledgeItem(
                    id="kb_3",
                    organization_id="org_apex_univ",
                    agent_id="agent_admission",
                    title="Admission Dates 2026",
                    content="BTech admissions for the 2026-27 academic session open on May 15, 2026 and close on July 31, 2026.",
                    category="dates"
                ),
                KnowledgeItem(
                    id="kb_4",
                    organization_id="org_apex_univ",
                    agent_id="agent_admission",
                    title="Hostel Facilities",
                    content="Separate AC and Non-AC hostels are available for boys and girls. Annual hostel fee is INR 80,000 including food.",
                    category="hostel"
                ),
            ],
            "org_zenith_college": [
                KnowledgeItem(
                    id="kb_5",
                    organization_id="org_zenith_college",
                    agent_id="agent_admission",
                    title="BBA Program Fees",
                    content="Zenith College offers BBA at INR 95,000 per year.",
                    category="fees"
                )
            ]
        }

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        if not query.organization_id:
            raise RAGError("organization_id is strictly required for retrieval")

        tenant_items = self._store.get(query.organization_id, [])
        from app.rag.normalizer import SemanticQueryNormalizer, SemanticIntent
        normalized = SemanticQueryNormalizer.normalize(query.query_text)
        
        matched: List[KnowledgeItem] = []
        
        # 1. Intent-targeted authoritative retrieval
        category_intent_map = {
            SemanticIntent.LIST_AVAILABLE_COURSES: ["fees", "courses", "general"],
            SemanticIntent.FEES_INQUIRY: ["fees"],
            SemanticIntent.ELIGIBILITY_INQUIRY: ["eligibility"],
            SemanticIntent.ADMISSION_DATES_INQUIRY: ["dates"],
            SemanticIntent.HOSTEL_INQUIRY: ["hostel"],
            SemanticIntent.CAMPUS_INQUIRY: ["general", "campus"]
        }
        
        target_categories = category_intent_map.get(normalized.intent, ["fees", "courses", "general", "eligibility"])
        for item in tenant_items:
            if item.category in target_categories:
                matched.append(item)
                
        # 2. Canonical search term matching if specific category matching produced nothing
        if not matched:
            search_terms = set(normalized.canonical_keywords) | set(query.query_text.lower().split())
            for item in tenant_items:
                if item in matched:
                    continue
                content_lower = item.content.lower() + " " + item.title.lower()
                if any(term.lower() in content_lower for term in search_terms if len(term) > 2):
                    matched.append(item)

        # Fallback to tenant items if no specific match so LLM always has institution grounding
        if not matched and tenant_items:
            matched = list(tenant_items)

        selected_items = matched[:query.top_k]
        
        logger.info(
            f"[GROUNDING]\n"
            f"intent={normalized.intent.value}\n"
            f"organization_id={query.organization_id}\n"
            f"agent_id={query.agent_id or 'default'}\n"
            f"sources={len(selected_items)}",
            extra={"organization_id": query.organization_id}
        )

        return RetrievalResult(
            items=selected_items,
            has_verified_info=len(selected_items) > 0
        )
