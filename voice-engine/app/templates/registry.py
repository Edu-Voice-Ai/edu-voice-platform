"""Agent Template Registry for instantaneous zero-latency template resolution."""
from typing import Dict, Type, Optional, Any
from app.templates.base import BaseAgentTemplate, AgentConfig
from app.templates.education import EducationTemplate
from app.templates.appointment_booking import AppointmentBookingTemplate
from app.templates.real_estate import RealEstateTemplate
from app.templates.sales_discovery import SalesDiscoveryTemplate
from app.templates.emi_collection import EMICollectionTemplate
from app.templates.healthcare_renewal import HealthcareRenewalTemplate
from app.templates.ecommerce_cart import EcommerceCartTemplate
from app.templates.order_delivery import OrderDeliveryTemplate
from app.templates.subscription_renewal import SubscriptionRenewalTemplate
from app.templates.custom import CustomTemplate
from app.core.logging import get_logger

logger = get_logger("templates.registry")


class AgentTemplateRegistry:
    """Registry maintaining instances of the 10 core multi-industry agent templates."""

    _TEMPLATES: Dict[str, BaseAgentTemplate] = {}

    @classmethod
    def initialize(cls):
        """Register all 10 standard agent templates."""
        cls._TEMPLATES = {
            "education": EducationTemplate(),
            "appointment_booking": AppointmentBookingTemplate(),
            "real_estate": RealEstateTemplate(),
            "sales_discovery": SalesDiscoveryTemplate(),
            "emi_collection": EMICollectionTemplate(),
            "healthcare_renewal": HealthcareRenewalTemplate(),
            "ecommerce_cart": EcommerceCartTemplate(),
            "order_delivery": OrderDeliveryTemplate(),
            "subscription_renewal": SubscriptionRenewalTemplate(),
            "custom": CustomTemplate(),
        }
        logger.info(f"[TEMPLATE_REGISTRY] Initialized {len(cls._TEMPLATES)} agent templates")

    @classmethod
    def get_template(cls, template_type: Optional[str] = None) -> BaseAgentTemplate:
        """Resolve template instance by name. Defaults to 'education' baseline if unspecified or unknown."""
        if not cls._TEMPLATES:
            cls.initialize()

        norm_key = (template_type or "education").lower().strip()
        template = cls._TEMPLATES.get(norm_key)

        if not template:
            logger.warning(f"[TEMPLATE_REGISTRY] Unknown template '{template_type}'; falling back to 'education'")
            return cls._TEMPLATES["education"]

        return template

    @classmethod
    def list_templates(cls) -> Dict[str, str]:
        """Return dict of template_type to persona title."""
        if not cls._TEMPLATES:
            cls.initialize()
        return {k: v.default_persona_title for k, v in cls._TEMPLATES.items()}

    @classmethod
    def create_agent_config(
        cls,
        template_type: str = "education",
        agent_id: str = "agent_default",
        organization_id: str = "org_default",
        business_name: Optional[str] = None,
        agent_name: Optional[str] = None,
        language: str = "en-IN",
        **kwargs
    ) -> AgentConfig:
        """Factory method to construct an AgentConfig with sensible template defaults."""
        template = cls.get_template(template_type)
        return AgentConfig(
            agent_id=agent_id,
            organization_id=organization_id,
            template_type=template.template_type,
            agent_name=agent_name or template.default_agent_name,
            business_name=business_name or template.default_business_name,
            language=language,
            **kwargs
        )


# Pre-initialize singleton on module load for instant in-memory availability
AgentTemplateRegistry.initialize()
