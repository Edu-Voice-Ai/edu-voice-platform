"""Comprehensive developer test suite for the 10 multi-industry Agent Templates."""
import pytest
import asyncio
from app.templates.registry import AgentTemplateRegistry
from app.templates.base import BaseAgentTemplate, AgentConfig
from app.session.state import SessionState
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.conversation.manager import ConversationManager


class TestMultiIndustryTemplates:

    def test_registry_resolves_all_10_templates(self):
        """Verify that all 10 agent templates are registered and resolve cleanly."""
        expected_templates = [
            "education",
            "appointment_booking",
            "real_estate",
            "sales_discovery",
            "emi_collection",
            "healthcare_renewal",
            "ecommerce_cart",
            "order_delivery",
            "subscription_renewal",
            "custom"
        ]
        registered = AgentTemplateRegistry.list_templates()
        for t in expected_templates:
            assert t in registered, f"Template '{t}' missing from AgentTemplateRegistry"
            template_obj = AgentTemplateRegistry.get_template(t)
            assert isinstance(template_obj, BaseAgentTemplate)
            assert template_obj.template_type == t

    def test_default_fallback_to_education(self):
        """Verify that omitting template_type or providing unknown string defaults to Education."""
        t_none = AgentTemplateRegistry.get_template(None)
        assert t_none.template_type == "education"
        assert t_none.default_business_name == "Apex University"

        t_unknown = AgentTemplateRegistry.get_template("unknown_industry_xyz")
        assert t_unknown.template_type == "education"

        session = SessionState(session_id="s_default", organization_id="org_test", agent_id="ag_test")
        assert session.template_type == "education"
        assert session.business_name == "Apex University"
        assert session.institution_name == "Apex University"
        assert "Apex University" in session.get_greeting_text()

    def test_session_institution_name_backward_compatibility(self):
        """Verify that institution_name is fully synced with business_name in SessionState."""
        s1 = SessionState(session_id="s1", organization_id="o1", agent_id="a1", business_name="City Clinic")
        assert s1.institution_name == "City Clinic"
        assert s1.business_name == "City Clinic"

        s2 = SessionState(session_id="s2", organization_id="o2", agent_id="a2", institution_name="Metro Hospital")
        assert s2.business_name == "Metro Hospital"
        assert s2.institution_name == "Metro Hospital"

    def test_education_template_baseline(self):
        """Verify Education baseline preserves existing admission counselor behavior and tools."""
        t = AgentTemplateRegistry.get_template("education")
        session = SessionState(
            session_id="s_edu",
            organization_id="org_apex_univ",
            agent_id="agent_admission",
            template_type="education",
            business_name="Apex University"
        )
        prompt = t.get_system_prompt(session, verified_context="CSE fee 1,50,000", lang="en-IN")
        assert "Priya" in prompt
        assert "Apex University" in prompt
        assert "Admission Voice Counselor" in prompt

        tools = t.get_tool_registry()
        assert tools.get_tool("get_courses") is not None
        assert tools.get_tool("get_fee") is not None
        assert tools.get_tool("get_eligibility") is not None
        assert tools.get_tool("get_admission_dates") is not None
        assert tools.get_tool("create_lead") is not None

        assert t.is_domain_query("What is the B.Tech CSE fee?")
        assert t.is_domain_query("మీ దగ్గర ఏమేమి courses ఉన్నాయి?")

    @pytest.mark.asyncio
    async def test_appointment_booking_template(self):
        """Verify Appointment Booking persona, prompt, and tool execution."""
        t = AgentTemplateRegistry.get_template("appointment_booking")
        session = SessionState(
            session_id="s_apt",
            organization_id="org_clinic",
            agent_id="agent_apt",
            template_type="appointment_booking",
            business_name="City Clinic"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Ananya" in prompt
        assert "City Clinic" in prompt
        assert "Appointment Assistant" in prompt
        assert "appointments" in prompt.lower()
        # Verify no university leakage
        assert "Apex University" not in prompt
        assert "B.Tech" not in prompt

        tools = t.get_tool_registry()
        assert tools.get_tool("get_services") is not None
        assert tools.get_tool("check_availability") is not None
        assert tools.get_tool("create_appointment") is not None

        # Execute check_availability tool
        check_tool = tools.get_tool("check_availability")
        res = await check_tool.execute("org_clinic", "agent_apt", preferred_date="2026-09-10")
        assert res.success is True
        assert "available_slots" in res.data

        # Execute create_appointment tool
        book_tool = tools.get_tool("create_appointment")
        book_res = await book_tool.execute(
            "org_clinic",
            "agent_apt",
            patient_name="Suresh Kumar",
            phone_number="9876543210",
            service="Dental",
            date="2026-09-10",
            time_slot="10:30 AM"
        )
        assert book_res.success is True
        assert book_res.data["status"] == "CONFIRMED"

        assert t.is_domain_query("I want to book an appointment with a dentist")
        assert t.is_domain_query("నాకు డాక్టర్ అపాయింట్మెంట్ కావాలి")

    @pytest.mark.asyncio
    async def test_real_estate_template(self):
        """Verify Real Estate persona, property search, and site visit scheduling."""
        t = AgentTemplateRegistry.get_template("real_estate")
        session = SessionState(
            session_id="s_re",
            organization_id="org_realty",
            agent_id="agent_re",
            template_type="real_estate",
            business_name="Skyline Realty"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Rahul" in prompt
        assert "Skyline Realty" in prompt
        assert "Property Consultant" in prompt
        assert "Apex University" not in prompt

        tools = t.get_tool_registry()
        assert tools.get_tool("search_properties") is not None
        assert tools.get_tool("schedule_site_visit") is not None

        search_tool = tools.get_tool("search_properties")
        res = await search_tool.execute("org_realty", "agent_re", location="Banjara Hills")
        assert res.success is True
        assert len(res.data["properties"]) >= 1

        assert t.is_domain_query("I am looking for a 2BHK flat in Hyderabad")
        assert t.is_domain_query("నాకు 3BHK విల్లా కావాలి")

    @pytest.mark.asyncio
    async def test_sales_discovery_template(self):
        """Verify Sales Discovery lead qualification and product plans."""
        t = AgentTemplateRegistry.get_template("sales_discovery")
        session = SessionState(
            session_id="s_sales",
            organization_id="org_saas",
            agent_id="agent_sales",
            template_type="sales_discovery",
            business_name="CloudTech AI"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Aarav" in prompt
        assert "CloudTech AI" in prompt
        assert "Sales Assistant" in prompt

        tools = t.get_tool_registry()
        plan_tool = tools.get_tool("get_product_information")
        res = await plan_tool.execute("org_saas", "agent_sales", product_name="Voice AI Platform")
        assert res.success is True
        assert len(res.data["plans"]) >= 2

        assert t.is_domain_query("What is the software pricing for enterprise?")

    @pytest.mark.asyncio
    async def test_emi_collection_template(self):
        """Verify EMI Collection reminder and promise-to-pay (strictly safe mock)."""
        t = AgentTemplateRegistry.get_template("emi_collection")
        session = SessionState(
            session_id="s_emi",
            organization_id="org_nbfc",
            agent_id="agent_emi",
            template_type="emi_collection",
            business_name="FastCredit Finance"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Arjun" in prompt
        assert "FastCredit Finance" in prompt
        assert "Payment Assistant" in prompt

        tools = t.get_tool_registry()
        due_tool = tools.get_tool("get_due_information")
        res = await due_tool.execute("org_nbfc", "agent_emi", account_id="ACC-99")
        assert res.success is True
        assert "due_amount_inr" in res.data

        ptp_tool = tools.get_tool("record_promise_to_pay")
        ptp_res = await ptp_tool.execute("org_nbfc", "agent_emi", ptp_date="2026-09-15")
        assert ptp_res.success is True
        assert ptp_res.data["status"] == "CONFIRMED"

        assert t.is_domain_query("When is my next EMI installment due?")

    @pytest.mark.asyncio
    async def test_healthcare_renewal_template(self):
        """Verify Healthcare & Policy Renewal with strict medical safety guardrails."""
        t = AgentTemplateRegistry.get_template("healthcare_renewal")
        session = SessionState(
            session_id="s_health",
            organization_id="org_insure",
            agent_id="agent_health",
            template_type="healthcare_renewal",
            business_name="Shield Health Insurance"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Meera" in prompt
        assert "Shield Health Insurance" in prompt
        assert "Renewal Assistant" in prompt
        assert "NEVER provide medical diagnosis" in prompt

        tools = t.get_tool_registry()
        policy_tool = tools.get_tool("get_renewal_details")
        res = await policy_tool.execute("org_insure", "agent_health", policy_id="POL-888")
        assert res.success is True
        assert "coverage_sum_insured_inr" in res.data

        assert t.is_domain_query("When does my health insurance policy expire?")

    @pytest.mark.asyncio
    async def test_ecommerce_cart_template(self):
        """Verify Ecommerce Cart Recovery tools and inquiry handling."""
        t = AgentTemplateRegistry.get_template("ecommerce_cart")
        session = SessionState(
            session_id="s_ecom",
            organization_id="org_store",
            agent_id="agent_cart",
            template_type="ecommerce_cart",
            business_name="Trendz Lifestyle"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Kavya" in prompt
        assert "Trendz Lifestyle" in prompt
        assert "Shopping Assistant" in prompt

        tools = t.get_tool_registry()
        cart_tool = tools.get_tool("get_cart")
        res = await cart_tool.execute("org_store", "agent_cart", cart_id="CART-77")
        assert res.success is True
        assert len(res.data["items"]) >= 1

        assert t.is_domain_query("I left some items in my shopping cart")

    @pytest.mark.asyncio
    async def test_order_delivery_template(self):
        """Verify Order Delivery tracking and support request creation."""
        t = AgentTemplateRegistry.get_template("order_delivery")
        session = SessionState(
            session_id="s_order",
            organization_id="org_courier",
            agent_id="agent_order",
            template_type="order_delivery",
            business_name="Express Courier"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Ravi" in prompt
        assert "Express Courier" in prompt
        assert "Customer Support Assistant" in prompt

        tools = t.get_tool_registry()
        track_tool = tools.get_tool("get_delivery_status")
        res = await track_tool.execute("org_courier", "agent_order", order_id="ORD-101")
        assert res.success is True
        assert "tracking_number" in res.data

        assert t.is_domain_query("Where is my package arriving?")

    @pytest.mark.asyncio
    async def test_subscription_renewal_template(self):
        """Verify Subscription Renewal upgrade and tier comparison."""
        t = AgentTemplateRegistry.get_template("subscription_renewal")
        session = SessionState(
            session_id="s_sub",
            organization_id="org_saas",
            agent_id="agent_sub",
            template_type="subscription_renewal",
            business_name="StreamPlus Media"
        )
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Neha" in prompt
        assert "StreamPlus Media" in prompt
        assert "Subscription Assistant" in prompt

        tools = t.get_tool_registry()
        plan_tool = tools.get_tool("get_plan_details")
        res = await plan_tool.execute("org_saas", "agent_sub", target_plan="Premium")
        assert res.success is True
        assert len(res.data["plans"]) >= 2

        assert t.is_domain_query("My subscription is expiring next week")

    def test_custom_template_with_injected_configuration(self):
        """Verify Custom Template accepts arbitrary persona, prompt, and greeting overrides."""
        session = SessionState(
            session_id="s_custom",
            organization_id="org_custom",
            agent_id="agent_travel",
            template_type="custom",
            business_name="Global Travel Agency",
            agent_name="Vikram",
            system_prompt="You are Vikram, the lead flight booking agent for Global Travel Agency. Help with flights.",
            greeting_message="Hello from Global Travel Agency! Where would you like to fly today?",
            goodbye_message="Thank you for booking with Global Travel Agency. Safe travels!"
        )
        t = AgentTemplateRegistry.get_template("custom")
        prompt = t.get_system_prompt(session, lang="en-IN")
        assert "Vikram" in prompt
        assert "Global Travel Agency" in prompt
        assert "Help with flights" in prompt

        assert session.get_greeting_text() == "Hello from Global Travel Agency! Where would you like to fly today?"
        assert session.get_goodbye_text() == "Thank you for booking with Global Travel Agency. Safe travels!"

    @pytest.mark.asyncio
    async def test_cross_industry_isolation_no_education_leakage(self):
        """CRITICAL: Verify non-education templates NEVER trigger Apex University B.Tech answers or unoffered course refusals."""
        non_edu_templates = [
            ("appointment_booking", "City Clinic"),
            ("real_estate", "ABC Realty"),
            ("sales_discovery", "ABC Solutions"),
            ("emi_collection", "ABC Finance"),
            ("healthcare_renewal", "ABC Health"),
            ("ecommerce_cart", "ABC Store"),
            ("order_delivery", "ABC Delivery"),
            ("subscription_renewal", "ABC Subscriptions"),
            ("custom", "Custom Corp")
        ]

        for temp_name, biz_name in non_edu_templates:
            session = SessionState(
                session_id=f"s_iso_{temp_name}",
                organization_id="org_iso",
                agent_id="ag_iso",
                template_type=temp_name,
                business_name=biz_name
            )

            # 1. Check MBA unoffered program query: In Education this triggers unoffered refusal.
            # In non-education templates, it MUST NOT trigger unoffered refusal!
            complexity, fast_resp = await FastQueryRouter.route_and_resolve_fast_path(
                session=session,
                user_text="Do you offer MBA?",
                rag_provider=None
            )
            assert fast_resp is None or "Apex University" not in fast_resp
            assert fast_resp is None or "B.Tech" not in fast_resp
            assert complexity == QueryComplexity.COMPLEX

            # 2. Check CSE fee query: In Education this triggers 1,50,000 INR fast answer.
            # In non-education templates, it MUST NOT return Apex University CSE fee!
            complexity2, fast_resp2 = await FastQueryRouter.route_and_resolve_fast_path(
                session=session,
                user_text="What is the CSE fee?",
                rag_provider=None
            )
            assert fast_resp2 is None
            assert complexity2 == QueryComplexity.COMPLEX

    @pytest.mark.asyncio
    async def test_education_still_resolves_fast_path_accurately(self):
        """Verify Education template DOES continue to resolve verified unoffered course refusal."""
        edu_session = SessionState(
            session_id="s_edu_fast",
            organization_id="org_apex_univ",
            agent_id="agent_admission",
            template_type="education",
            business_name="Apex University"
        )
        complexity, fast_resp = await FastQueryRouter.route_and_resolve_fast_path(
            session=edu_session,
            user_text="Do you offer MBA?",
            rag_provider=None
        )
        assert complexity == QueryComplexity.SIMPLE
        assert fast_resp is not None
        assert "B.Tech in CSE and ECE" in fast_resp

    def test_multilingual_greetings_across_templates(self):
        """Verify Telugu and Hindi greetings function properly across templates."""
        templates_to_test = ["education", "appointment_booking", "real_estate", "ecommerce_cart"]
        for t_name in templates_to_test:
            session_te = SessionState(
                session_id=f"s_te_{t_name}",
                organization_id="org_te",
                agent_id="ag_te",
                template_type=t_name,
                language="te-IN",
                preferred_language="te-IN"
            )
            te_greeting = session_te.get_greeting_text()
            assert len(te_greeting) > 10

            session_hi = SessionState(
                session_id=f"s_hi_{t_name}",
                organization_id="org_hi",
                agent_id="ag_hi",
                template_type=t_name,
                language="hi-IN",
                preferred_language="hi-IN"
            )
            hi_greeting = session_hi.get_greeting_text()
            assert len(hi_greeting) > 10

    @pytest.mark.asyncio
    async def test_build_default_engine_across_templates(self):
        """Verify build_default_engine creates SpeechToSpeechEngine with template-scoped tools."""
        from app.api.websocket import build_default_engine

        test_cases = [
            ("education", "get_courses"),
            ("appointment_booking", "create_appointment"),
            ("real_estate", "search_properties"),
            ("sales_discovery", "qualify_lead"),
            ("emi_collection", "record_promise_to_pay"),
            ("healthcare_renewal", "get_renewal_details"),
            ("ecommerce_cart", "get_cart"),
            ("order_delivery", "get_delivery_status"),
            ("subscription_renewal", "get_subscription"),
            ("custom", "request_human_handoff"),
        ]

        for temp_name, expected_tool in test_cases:
            session = SessionState(
                session_id=f"s_eng_{temp_name}",
                organization_id="org_test",
                agent_id="ag_test",
                template_type=temp_name,
                business_name=f"Test {temp_name}"
            )
            engine = build_default_engine(session)
            try:
                assert engine is not None
                assert engine.conversation_manager is not None
                assert engine.conversation_manager.tool_registry is not None
                tool = engine.conversation_manager.tool_registry.get_tool(expected_tool)
                assert tool is not None, f"Expected tool {expected_tool} not found in {temp_name} engine registry"
            finally:
                await engine.stop()

