"""Multi-industry Agent Templates package."""
from app.templates.base import BaseAgentTemplate, AgentConfig, BusinessConfiguration
from app.templates.registry import AgentTemplateRegistry
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

__all__ = [
    "BaseAgentTemplate",
    "AgentConfig",
    "BusinessConfiguration",
    "AgentTemplateRegistry",
    "EducationTemplate",
    "AppointmentBookingTemplate",
    "RealEstateTemplate",
    "SalesDiscoveryTemplate",
    "EMICollectionTemplate",
    "HealthcareRenewalTemplate",
    "EcommerceCartTemplate",
    "OrderDeliveryTemplate",
    "SubscriptionRenewalTemplate",
    "CustomTemplate",
]
