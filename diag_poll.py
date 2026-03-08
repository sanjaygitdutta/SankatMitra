import boto3, json, os
from dotenv import load_dotenv
load_dotenv()

lam = boto3.client('lambda', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))
ddb = boto3.resource('dynamodb', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

# 1. Test GET /corridor/corridors (no auth - simulating civilian)
print("=== GET /corridor/corridors (no auth) ===")
resp = lam.invoke(FunctionName='sankatmitra-corridor-lambda',
    InvocationType='RequestResponse',
    Payload=json.dumps({'path': '/corridor/corridors', 'httpMethod': 'GET', 'headers': {}, 'body': '{}'}))
result = json.loads(resp['Payload'].read())
print(f"HTTP {result.get('statusCode')}:")
body = json.loads(result.get('body', '{}'))
corridors = body.get('corridors', [])
print(f"Active corridors: {len(corridors)}")
for c in corridors:
    print(f"  ID={c.get('corridorId','?')[:20]} vehicle={c.get('emergencyVehicleId','?')} ambLat={c.get('ambulanceLat','N/A')} ambLon={c.get('ambulanceLon','N/A')}")

# 2. Check LocationHistory for ambulance entries
print("\n=== LocationHistory (AMBULANCE entries) ===")
table = ddb.Table('SankatMitra-LocationHistory-v2')
resp2 = table.scan(Limit=20)
items = resp2.get('Items', [])
print(f"Total rows: {len(items)}")
for item in items:
    vtype = item.get('vehicleType', item.get('type', 'N/A'))
    vid = item.get('vehicleId', 'N/A')
    lat = item.get('latitude', 'N/A')
    lon = item.get('longitude', 'N/A')
    print(f"  {vid} | {vtype} | lat={lat} lon={lon}")
