import os
import httpx
import json
import base64
from dotenv import load_dotenv

load_dotenv("voice-engine/.env")

ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
API_KEY = os.getenv("EXOTEL_API_KEY")
API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
BASE_URL = os.getenv("EXOTEL_BASE_URL", "https://api.exotel.com")

if not ACCOUNT_SID or not API_KEY or not API_TOKEN:
    print("Error: EXOTEL_ACCOUNT_SID, EXOTEL_API_KEY, or EXOTEL_API_TOKEN not configured in .env")
    exit(1)

auth_header = base64.b64encode(f"{API_KEY}:{API_TOKEN}".encode()).decode()
headers = {
    "Authorization": f"Basic {auth_header}",
    "Accept": "application/json"
}

print(f"Testing Exotel Account SID: {ACCOUNT_SID}")

endpoints = [
    f"{BASE_URL}/v1/Accounts/{ACCOUNT_SID}",
    f"{BASE_URL}/v1/Accounts/{ACCOUNT_SID}/Numbers",
    f"{BASE_URL}/v1/Accounts/{ACCOUNT_SID}/IncomingPhoneNumbers",
    f"{BASE_URL}/v1/Accounts/{ACCOUNT_SID}/Apps",
]

with httpx.Client(timeout=10.0) as client:
    for ep in endpoints:
        try:
            resp = client.get(ep, headers=headers)
            print(f"\nGET {ep} -> Status: {resp.status_code}")
            try:
                data = resp.json()
                print("Response JSON:")
                print(json.dumps(data, indent=2))
            except Exception:
                print("Response Text:", resp.text[:500])
        except Exception as e:
            print(f"Error querying {ep}: {e}")
