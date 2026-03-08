import boto3, os, json, time
from dotenv import load_dotenv
load_dotenv()
lam = boto3.client('lambda', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

# Auth
auth = lam.invoke(FunctionName='sankatmitra-auth-lambda',
    InvocationType='RequestResponse',
    Payload=json.dumps({'path': '/auth/login', 'httpMethod': 'POST', 'headers': {},
        'body': json.dumps({'vehicleId': 'AMB-IND-002', 'registrationNumber': 'DL-01-CD-5678', 'agencyId': 'AGENCY-DEL-02'})}))
token = json.loads(json.loads(auth['Payload'].read()).get('body', '{}')).get('token', '')
print('Auth OK:', token[:20] + '...')

# Push ambulance GPS (Kolkata New Town area - same as ambulance app)
gps = lam.invoke(FunctionName='sankatmitra-gps-lambda',
    InvocationType='RequestResponse',
    Payload=json.dumps({'path': '/gps/update', 'httpMethod': 'POST', 'headers': {},
        'body': json.dumps({
            'vehicleId': 'AMB-IND-002', 'type': 'AMBULANCE', 'fcmToken': '',
            'coordinate': {'latitude': 22.5749, 'longitude': 88.4345,
                'accuracy': 5.0, 'timestamp': '2026-03-07T08:30:00Z'},
            'satelliteCount': 10, 'signalStrength': -65.0
        })}))
gps_r = json.loads(gps['Payload'].read())
print('GPS push HTTP:', gps_r.get('statusCode'))

# Activate corridor
corr = lam.invoke(FunctionName='sankatmitra-corridor-lambda',
    InvocationType='RequestResponse',
    Payload=json.dumps({'path': '/corridor/activate', 'httpMethod': 'POST',
        'headers': {'Authorization': f'Bearer {token}'},
        'body': json.dumps({
            'currentLocation': {'latitude': 22.5749, 'longitude': 88.4345, 'accuracy': 5.0, 'timestamp': '2026-03-07T08:30:00Z'},
            'destination': {'latitude': 22.5761, 'longitude': 88.4731},
            'urgencyLevel': 'HIGH', 'missionType': 'EMERGENCY'
        })}))
corr_body = json.loads(json.loads(corr['Payload'].read()).get('body', '{}'))
print('Corridor HTTP:', json.loads(corr['Payload'].read() or '{}'))
print('Corridor ID:', str(corr_body.get('corridorId', '?'))[:30])

time.sleep(1)

# Check GET /corridor/corridors
list_r = lam.invoke(FunctionName='sankatmitra-corridor-lambda',
    InvocationType='RequestResponse',
    Payload=json.dumps({'path': '/corridor/corridors', 'httpMethod': 'GET', 'headers': {}, 'body': '{}'}))
list_body = json.loads(json.loads(list_r['Payload'].read()).get('body', '{}'))
corridors = list_body.get('corridors', [])
print('Active corridors:', len(corridors))
for c in corridors:
    vid = c.get('emergencyVehicleId', '?')
    lat = c.get('ambulanceLat', 'MISSING')
    lon = c.get('ambulanceLon', 'MISSING')
    print('  vehicle=' + vid + ' ambLat=' + lat + ' ambLon=' + lon[:10])
