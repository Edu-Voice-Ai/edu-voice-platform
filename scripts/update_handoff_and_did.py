"""
Database update script to configure authorized human handoff number and ensure DIDs are mapped.
"""
import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TARGET_HANDOFF_NUMBER = "+918121161040"
MAYA_AGENT_ID = "c0000000-0000-0000-0000-000000000001"
APEX_ORG_ID = "a0000000-0000-0000-0000-000000000001"
DID_1 = "+919513886363"  # Canonical active DID for Maya (migrated from DID_2)
RETIRED_OLD_DID_1 = "+914045901132"  # Retired old DID

def mask_phone(num: str | None) -> str:
    if not num:
        return "None"
    if len(num) > 6:
        return num[:3] + "******" + num[-4:]
    return "***"

async def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set in environment.")
        sys.exit(1)

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        # 1. Update Maya's agent config with authorized human handoff number
        print("Updating Maya's agent_config...")
        update_stmt = text("""
            UPDATE agent_configs
            SET human_handoff_enabled = true,
                human_handoff_number = :handoff_num,
                human_handoff_condition = 'on_request_or_unknown',
                updated_at = NOW()
            WHERE agent_id = :agent_id;
        """)
        res = await conn.execute(update_stmt, {
            "handoff_num": TARGET_HANDOFF_NUMBER,
            "agent_id": MAYA_AGENT_ID,
        })
        print(f"agent_configs rows updated: {res.rowcount}")

        # 2. Ensure canonical DID_1 (+919513886363) exists and is active
        check_phone = await conn.execute(
            text("SELECT id FROM phone_numbers WHERE phone_number = :phone"),
            {"phone": DID_1}
        )
        row = check_phone.fetchone()
        did1_id = "b0000000-0000-0000-0000-000000000002"
        if not row:
            print(f"Inserting {DID_1} into phone_numbers...")
            await conn.execute(text("""
                INSERT INTO phone_numbers (id, organization_id, phone_number, provider, provider_sid, country_code, status, created_at, updated_at)
                VALUES (:id, :org_id, :phone, 'exotel', 'eduvoiceagent1', 'IN', 'active', NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET phone_number = :phone, status = 'active';
            """), {"id": did1_id, "org_id": APEX_ORG_ID, "phone": DID_1})
        else:
            did1_id = str(row[0])
            await conn.execute(text("""
                UPDATE phone_numbers SET status = 'active', updated_at = NOW() WHERE id = :id;
            """), {"id": did1_id})

        # Ensure active assignment for canonical DID_1 -> Maya
        await conn.execute(text("""
            INSERT INTO phone_assignments (id, organization_id, phone_number_id, agent_id, is_active, created_at, updated_at)
            VALUES ('d0000000-0000-0000-0000-000000000002', :org_id, :phone_id, :agent_id, true, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET is_active = true, agent_id = :agent_id;
        """), {"org_id": APEX_ORG_ID, "phone_id": did1_id, "agent_id": MAYA_AGENT_ID})
        print(f"Activated canonical assignment for {DID_1} -> Maya.")

        # 3. Deactivate retired old DID_1 (+914045901132)
        print(f"Deactivating retired old DID {RETIRED_OLD_DID_1}...")
        await conn.execute(text("""
            UPDATE phone_assignments
            SET is_active = false, updated_at = NOW()
            WHERE phone_number_id IN (SELECT id FROM phone_numbers WHERE phone_number = :old_phone);
        """), {"old_phone": RETIRED_OLD_DID_1})
        await conn.execute(text("""
            UPDATE phone_numbers
            SET status = 'released', updated_at = NOW()
            WHERE phone_number = :old_phone;
        """), {"old_phone": RETIRED_OLD_DID_1})
        print(f"Deactivated retired old DID {RETIRED_OLD_DID_1}.")

        # 3. Verification query
        verify_stmt = text("""
            SELECT ac.id, ac.agent_id, ac.human_handoff_enabled, ac.human_handoff_number, ac.human_handoff_condition
            FROM agent_configs ac
            WHERE ac.agent_id = :agent_id;
        """)
        verify_res = await conn.execute(verify_stmt, {"agent_id": MAYA_AGENT_ID})
        for r in verify_res.mappings().all():
            print("Verified Agent Config:", {
                "id": str(r["id"]),
                "agent_id": str(r["agent_id"]),
                "enabled": r["human_handoff_enabled"],
                "number": mask_phone(r["human_handoff_number"]),
                "condition": r["human_handoff_condition"],
            })

    await engine.dispose()
    print("Database update successfully committed.")

if __name__ == "__main__":
    asyncio.run(main())
