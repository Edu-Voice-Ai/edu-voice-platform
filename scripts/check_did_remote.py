import json
import os
import urllib.error
import urllib.request

url = os.environ.get("BACKEND_INTERNAL_URL", "http://edu-voice-ai-backend:8000") + "/api/v1/internal/telephony/resolve-did"
key = os.environ.get("INTERNAL_SERVICE_KEY", "") or os.environ.get("TELEPHONY_INTERNAL_SERVICE_KEY", "")

for phone in ["+914045901132", "+919513886363", "095-138-86363", "040-459-01132"]:
    req = urllib.request.Request(
        url,
        data=json.dumps({"phone_number": phone}).encode(),
        headers={"Content-Type": "application/json", "X-Internal-Service-Key": key}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())["data"]
            h = data.get("handoff_config", {})
            num = h.get("human_handoff_number")
            masked = (num[:3] + "******" + num[-4:]) if num else "None"
            agent = data.get("agent_name")
            enabled = h.get("human_handoff_enabled")
            print(f"{phone} -> SUCCESS: Agent={agent}, HandoffEnabled={enabled}, HandoffNum={masked}")
    except urllib.error.HTTPError as e:
        print(f"{phone} -> HTTPError {e.code}: {e.read().decode()[:120]}")
    except Exception as e:
        print(f"{phone} -> ERROR: {e}")
