import requests
import json
from datetime import datetime

BASE_URL = "https://r0bh4n62b6.execute-api.ap-south-1.amazonaws.com/prod"

print("Loging in with AMB-IND-002...")
login_payload = {
    "vehicleId": "AMB-IND-002",
    "registrationNumber": "DL-01-CD-5678",
    "agencyId": "AGENCY-DEL-02",
    "digitalSignature": "test_signature"
}

resp = requests.post(f"{BASE_URL}/auth/login", json=login_payload)
print(f"Login Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Login Failed: {resp.text}")
    exit(1)

token = resp.json().get('token')
print("Successfully got token. Activating corridor...")

headers = {'Authorization': f'Bearer {token}'}
activate_payload = {
    "currentLocation": {
        "latitude": 22.5726,
        "longitude": 88.3639,
        "accuracy": 10.0,
        "timestamp": datetime.now().isoformat()
    },
    "destination": {
        "latitude": 22.5761,
        "longitude": 88.4731
    },
    "urgencyLevel": "HIGH",
    "missionType": "EMERGENCY"
}

resp = requests.post(f"{BASE_URL}/corridor/activate", json=activate_payload, headers=headers)
print(f"Activate Status: {resp.status_code}")
print(f"Activate Response: {resp.text}")
