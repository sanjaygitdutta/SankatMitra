import boto3, json, os
from dotenv import load_dotenv
load_dotenv()

lam = boto3.client('lambda', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

payload = {
    'path': '/gps/update', 'httpMethod': 'POST', 'headers': {},
    'body': json.dumps({
        'vehicleId': 'CIV-TEST-001',
        'type': 'CIVILIAN',
        'fcmToken': 'demo-fcm-token-12345',
        'coordinate': {
            'latitude': 28.6139, 'longitude': 77.2090,
            'accuracy': 10.0,
            'timestamp': '2026-03-07T06:00:00Z'
        },
        'satelliteCount': 8,
        'signalStrength': -75.0,
    })
}
resp = lam.invoke(FunctionName='sankatmitra-gps-lambda',
    InvocationType='RequestResponse', Payload=json.dumps(payload),
    LogType='Tail')

import base64
raw = json.loads(resp['Payload'].read())
log = base64.b64decode(resp.get('LogResult', '')).decode('utf-8', errors='replace')
print('Status:', raw.get('statusCode'))
print('Body:', raw.get('body', '')[:300])
if raw.get('errorMessage'):
    print('ERROR:', raw.get('errorMessage'))
    for line in raw.get('stackTrace', []):
        print(line)
print('\n--- LOGS ---')
print(log[-2000:])
