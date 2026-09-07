"""
Edu-Voice-Ai — Internal Telephony & Voice Gateway Endpoints
Provides high-performance service-to-service DID resolution and call routing for Yasin's Voice Gateway.
"""

import re
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import AppException
from app.core.logging import logger
from app.db.session import get_db
from app.db.models.phone import PhoneNumber, PhoneAssignment
from app.db.models.organization import Organization
from app.db.models.agent import Agent, AgentConfig
from app.dependencies.auth import verify_internal_service_key
from app.schemas.common import SuccessResponse
from app.schemas.telephony import (
    DIDResolveRequest,
    DIDResolveResponse,
    SpeechConfig,
    HandoffConfig,
    OperatingHours,
)

router = APIRouter(prefix="/internal/telephony", tags=["Internal Telephony / Voice Gateway"])


def normalize_did(raw: str) -> str:
    """
    Normalizes Indian phone numbers into standard E.164 (+91XXXXXXXXXX) format.
    Accepts +918047361234, 918047361234, 08047361234, or 8047361234.
    Rejects malformed, non-numeric, or invalid length numbers with 422 INVALID_DID_FORMAT.
    """
    if not raw or not isinstance(raw, str):
        raise AppException(
            message="Phone number must be a non-empty string.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="INVALID_DID_FORMAT",
            details={"phone_number": raw},
        )

    # Strip whitespace and common punctuation
    cleaned = re.sub(r"[\s\-\(\)\.]", "", raw.strip())

    if cleaned.startswith("+91") and len(cleaned) == 13 and cleaned[3:].isdigit():
        return cleaned
    elif cleaned.startswith("91") and len(cleaned) == 12 and cleaned[2:].isdigit():
        return f"+{cleaned}"
    elif cleaned.startswith("0") and len(cleaned) == 11 and cleaned[1:].isdigit():
        return f"+91{cleaned[1:]}"
    elif len(cleaned) == 10 and cleaned.isdigit():
        return f"+91{cleaned}"
    else:
        raise AppException(
            message=f"Malformed or unsupported DID format: '{raw}'. Expected Indian E.164 (+91XXXXXXXXXX) or 10-digit number.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="INVALID_DID_FORMAT",
            details={"phone_number": raw},
        )


@router.post(
    "/resolve-did",
    response_model=SuccessResponse[DIDResolveResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_internal_service_key)],
)
async def resolve_did(
    payload: DIDResolveRequest,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[DIDResolveResponse]:
    """
    Internal service endpoint resolving incoming DID phone number to tenant, agent, and speech parameters.
    Protected by X-Internal-Service-Key with constant-time comparison.
    Enforces strict step-by-step resolution order:
      1. DID exists? (404)
      2. DID active? (403)
      3. Organization active? (403)
      4. Assignment exists & active? (422)
      5. Agent exists & active? (422)
      6. Agent config exists? (500)
      7. SUCCESS (200)
    """
    normalized_number = normalize_did(payload.phone_number)

    # Query phone number with tenant organization, assignment, agent, and config
    try:
        stmt = (
            select(PhoneNumber)
            .where(PhoneNumber.phone_number == normalized_number)
            .options(
                selectinload(PhoneNumber.organization),
                selectinload(PhoneNumber.assignment).selectinload(PhoneAssignment.agent).selectinload(Agent.config),
            )
        )
        result = await db.execute(stmt)
        phone = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.error(f"Database error during DID resolution for '{normalized_number}': {exc}")
        raise AppException(
            message="Authoritative database is currently unavailable. Please retry shortly.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="DATABASE_UNAVAILABLE",
            details={"phone_number": normalized_number},
        )

    # Step 1. Check DID Existence
    if not phone:
        logger.info(f"DID lookup failed: Phone number '{normalized_number}' not found.")
        raise AppException(
            message=f"The requested phone number '{normalized_number}' is not registered to any institution.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DID_NOT_FOUND",
            details={"phone_number": normalized_number},
        )

    # Step 2. Check DID Status
    if phone.status != "active":
        logger.info(f"DID lookup failed: Phone number '{normalized_number}' is {phone.status}.")
        raise AppException(
            message=f"Phone number '{normalized_number}' is currently {phone.status}.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="DID_INACTIVE",
            details={"phone_number": normalized_number, "status": phone.status},
        )

    # Step 3. Check Organization Active Status
    org: Organization = phone.organization
    if not org or not org.is_active:
        logger.info(f"DID lookup failed: Organization '{phone.organization_id}' is inactive.")
        raise AppException(
            message="The institution associated with this phone number is currently inactive.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="ORGANIZATION_INACTIVE",
            details={"organization_id": str(phone.organization_id)},
        )

    # Step 4. Check Active Assignment
    assignment: PhoneAssignment = phone.assignment
    if not assignment or not assignment.is_active:
        logger.info(f"DID lookup failed: Phone number '{normalized_number}' has no active assignment.")
        raise AppException(
            message=f"Phone number '{normalized_number}' does not have an active AI agent assignment.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="NO_ACTIVE_ASSIGNMENT",
            details={"phone_number": normalized_number, "organization_id": str(phone.organization_id)},
        )

    # Step 5. Check Agent Active Status
    agent: Agent = assignment.agent
    if not agent or not agent.is_active:
        logger.info(f"DID lookup failed: Agent for phone number '{normalized_number}' is inactive.")
        raise AppException(
            message="The AI agent assigned to this phone number is currently inactive.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="AGENT_INACTIVE",
            details={
                "phone_number": normalized_number,
                "agent_id": str(assignment.agent_id) if assignment else None,
                "organization_id": str(phone.organization_id),
            },
        )

    # Step 6. Check Agent Config
    config: AgentConfig = agent.config
    if not config:
        logger.error(f"DID resolution integrity error: Agent '{agent.id}' is missing agent_config.")
        raise AppException(
            message=f"Configuration data missing for agent '{agent.id}'.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="CONFIGURATION_ERROR",
            details={"agent_id": str(agent.id), "organization_id": str(phone.organization_id)},
        )

    # Step 7. Format canonical runtime response
    speech_config = SpeechConfig(
        primary_language=config.primary_language,
        supported_languages=config.supported_languages,
        voice_id=config.voice_id,
        voice_speed=float(config.voice_speed),
        allow_barge_in=config.allow_barge_in,
        vad_silence_threshold_ms=config.vad_silence_threshold_ms,
        welcome_message=config.welcome_message,
        max_call_duration_seconds=config.max_call_duration_seconds,
    )

    handoff_config = HandoffConfig(
        human_handoff_enabled=config.human_handoff_enabled,
        human_handoff_number=config.human_handoff_number,
        human_handoff_condition=config.human_handoff_condition,
    )

    operating_hours = OperatingHours(
        enabled=config.operating_hours.get("enabled", False) if config.operating_hours else False,
        timezone=config.operating_hours.get("timezone", "Asia/Kolkata") if config.operating_hours else "Asia/Kolkata",
        start_time=config.operating_hours.get("start_time", "09:00") if config.operating_hours else "09:00",
        end_time=config.operating_hours.get("end_time", "19:00") if config.operating_hours else "19:00",
        working_days=config.operating_hours.get("working_days", [1, 2, 3, 4, 5, 6]) if config.operating_hours else [1, 2, 3, 4, 5, 6],
    )

    response_data = DIDResolveResponse(
        found=True,
        phone_number=phone.phone_number,
        organization_id=org.id,
        organization_name=org.name,
        organization_slug=org.slug,
        agent_id=agent.id,
        agent_name=agent.name,
        agent_type=agent.agent_type,
        is_active=True,
        speech_config=speech_config,
        handoff_config=handoff_config,
        operating_hours=operating_hours,
    )

    return SuccessResponse(
        success=True,
        data=response_data,
        message="DID resolved successfully.",
    )
