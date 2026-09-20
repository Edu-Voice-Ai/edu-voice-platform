"""
Edu-Voice-Ai — Admission AI Agent & Config Endpoints
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.db.models.agent import Agent, AgentConfig
from app.db.models.organization import OrganizationMember
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_admin, require_org_member
from app.schemas.common import SuccessResponse
from app.schemas.agent import (
    AgentCreate,
    AgentResponse,
    AgentDetailResponse,
    AgentConfigResponse,
    AgentConfigUpdate,
)

router = APIRouter(prefix="/organizations/{organization_id}/agents", tags=["Admission AI Agents"])


@router.get("", response_model=SuccessResponse[List[AgentResponse]], status_code=status.HTTP_200_OK)
async def list_organization_agents(
    organization_id: UUID,
    membership: OrganizationMember = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[List[AgentResponse]]:
    """Lists all configured AI agents for the target organization."""
    stmt = (
        select(Agent)
        .where(Agent.organization_id == organization_id)
        .order_by(Agent.created_at.asc())
    )
    result = await db.execute(stmt)
    agents = result.scalars().all()

    return SuccessResponse(
        success=True,
        data=[AgentResponse.model_validate(a) for a in agents],
        message="Agents retrieved successfully.",
    )


@router.post("", response_model=SuccessResponse[AgentDetailResponse], status_code=status.HTTP_201_CREATED)
async def create_organization_agent(
    organization_id: UUID,
    payload: AgentCreate,
    membership: OrganizationMember = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[AgentDetailResponse]:
    """Creates a new AI agent and initializes default speech/prompt configurations (Admin/Owner only)."""
    agent = Agent(
        organization_id=organization_id,
        name=payload.name,
        agent_type=payload.agent_type,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(agent)
    await db.flush()

    config_data = payload.config.model_dump() if payload.config else {}
    agent_config = AgentConfig(
        agent_id=agent.id,
        organization_id=organization_id,
        primary_language=config_data.get("primary_language", "en-IN"),
        supported_languages=config_data.get("supported_languages", ["en-IN", "hi-IN", "te-IN"]),
        voice_id=config_data.get("voice_id", "qwen3_indian_female_1"),
        voice_speed=config_data.get("voice_speed", 1.00),
        system_prompt=config_data.get(
            "system_prompt",
            "You are a warm, professional admission counselor for an educational institution. Answer questions accurately based strictly on the provided knowledge base. If you do not know the answer, offer to connect the caller to a human counselor.",
        ),
        welcome_message=config_data.get(
            "welcome_message",
            "Hello! Thank you for calling our admissions office. How may I assist you today?",
        ),
        allow_barge_in=config_data.get("allow_barge_in", True),
        vad_silence_threshold_ms=config_data.get("vad_silence_threshold_ms", 400),
        human_handoff_enabled=config_data.get("human_handoff_enabled", True),
        human_handoff_number=config_data.get("human_handoff_number"),
        human_handoff_condition=config_data.get("human_handoff_condition", "on_request_or_unknown"),
        operating_hours=config_data.get(
            "operating_hours",
            {"enabled": False, "timezone": "Asia/Kolkata", "start_time": "09:00", "end_time": "19:00", "working_days": [1, 2, 3, 4, 5, 6]},
        ),
        max_call_duration_seconds=config_data.get("max_call_duration_seconds", 600),
        custom_settings=config_data.get("custom_settings", {}),
    )
    db.add(agent_config)
    await db.commit()
    await db.refresh(agent)
    await db.refresh(agent_config)

    response_data = AgentDetailResponse(
        id=agent.id,
        organization_id=agent.organization_id,
        name=agent.name,
        agent_type=agent.agent_type,
        description=agent.description,
        is_active=agent.is_active,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        config=AgentConfigResponse.model_validate(agent_config),
    )

    return SuccessResponse(
        success=True,
        data=response_data,
        message="Agent created successfully.",
    )


@router.get("/{agent_id}", response_model=SuccessResponse[AgentDetailResponse], status_code=status.HTTP_200_OK)
async def get_agent_detail(
    organization_id: UUID,
    agent_id: UUID,
    membership: OrganizationMember = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[AgentDetailResponse]:
    """Retrieves full agent details including speech parameters, voice, and prompts."""
    stmt = (
        select(Agent)
        .where(Agent.id == agent_id, Agent.organization_id == organization_id)
        .options(selectinload(Agent.config))
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if not agent:
        raise NotFoundException("Agent", str(agent_id))

    config_response = AgentConfigResponse.model_validate(agent.config) if agent.config else None

    return SuccessResponse(
        success=True,
        data=AgentDetailResponse(
            id=agent.id,
            organization_id=agent.organization_id,
            name=agent.name,
            agent_type=agent.agent_type,
            description=agent.description,
            is_active=agent.is_active,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            config=config_response,
        ),
        message="Agent details retrieved.",
    )


@router.patch("/{agent_id}/config", response_model=SuccessResponse[AgentConfigResponse], status_code=status.HTTP_200_OK)
async def update_agent_config(
    organization_id: UUID,
    agent_id: UUID,
    payload: AgentConfigUpdate,
    membership: OrganizationMember = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[AgentConfigResponse]:
    """Updates voice, prompt, speech, and barge-in settings for the agent (Admin/Owner only)."""
    stmt = select(AgentConfig).where(
        AgentConfig.agent_id == agent_id,
        AgentConfig.organization_id == organization_id,
    )
    config = (await db.execute(stmt)).scalar_one_or_none()
    if not config:
        raise NotFoundException("AgentConfig for agent", str(agent_id))

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    await db.commit()
    await db.refresh(config)

    return SuccessResponse(
        success=True,
        data=AgentConfigResponse.model_validate(config),
        message="Agent configuration updated successfully.",
    )
