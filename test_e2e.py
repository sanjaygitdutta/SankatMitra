import boto3, json, os, time
from dotenv import load_dotenv
load_dotenv()

lam = boto3.client('lambda', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

time.sleep(3)

# Step 1: Auth
auth_payload = {
    'path': '/auth/login', 'httpMethod': 'POST', 'headers': {},
    'body': json.dumps({'vehicleId': 'AMB-IND-002', 'registrationNumber': 'DL-01-CD-5678', 'agencyId': 'AGENCY-DEL-02'})
}
resp = lam.invoke(FunctionName='sankatmitra-auth-lambda', InvocationType='RequestResponse', Payload=json.dumps(auth_payload))
auth_result = json.loads(resp['Payload'].read())
auth_body = json.loads(auth_result.get('body', '{}'))
token = auth_body.get('token', '')
print(f"Auth: HTTP {auth_result.get('statusCode')} | token={token[:20]}...")

# Step 2: Corridor Activate
corridor_payload = {
    'path': '/corridor/activate', 'httpMethod': 'POST',
    'headers': {'Authorization': f'Bearer {token}'},
    'body': json.dumps({
        'currentLocation': {'latitude': 28.6139, 'longitude': 77.2090, 'accuracy': 10.0, 'timestamp': '2026-03-07T05:00:00Z'},
        'destination': {'latitude': 28.6304, 'longitude': 77.2177},
        'urgencyLevel': 'HIGH', 'missionType': 'EMERGENCY'
    })
}
resp2 = lam.invoke(FunctionName='sankatmitra-corridor-lambda', InvocationType='RequestResponse', Payload=json.dumps(corridor_payload))
corridor_result = json.loads(resp2['Payload'].read())
corridor_body = json.loads(corridor_result.get('body', '{}'))
cors = corridor_result.get('headers', {}).get('Access-Control-Allow-Origin', 'MISSING')
status = corridor_result.get('statusCode')
cid = corridor_body.get('corridorId', corridor_body.get('error', ''))[:40]
print(f"Corridor: HTTP {status} | CORS={cors} | result={cid}")
