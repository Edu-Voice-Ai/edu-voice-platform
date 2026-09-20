"""
Edu-Voice-Ai - API v1 Master Router
Aggregates all /api/v1 domain sub-routers under a unified namespace.
"""

from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.agents import router as agents_router
from app.api.v1.telephony import router as telephony_router
from app.api.v1.calls import router as calls_router
from app.api.v1.leads import router as leads_router
from app.api.v1.followups import router as followups_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.usage import router as usage_router
from app.api.v1.internal.telephony import router as internal_telephony_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(organizations_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(telephony_router)
api_v1_router.include_router(calls_router)
api_v1_router.include_router(leads_router)
api_v1_router.include_router(followups_router)
api_v1_router.include_router(knowledge_router)
api_v1_router.include_router(usage_router)
api_v1_router.include_router(internal_telephony_router)
