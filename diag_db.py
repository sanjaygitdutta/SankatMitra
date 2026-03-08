import boto3, os, requests, json
from dotenv import load_dotenv
load_dotenv()

ddb = boto3.resource('dynamodb', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

# 1. Check LocationHistory key schema
ddb_client = boto3.client('dynamodb', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))
desc = ddb_client.describe_table(TableName='SankatMitra-LocationHistory-v2')
keys = desc['Table']['KeySchema']
print("LocationHistory key schema:")
for k in keys:
    print(f"  {k['AttributeName']} ({k['KeyType']})")

# 2. Query latest AMB-IND-002 entry using hash key only
print("\nQuery AMB-IND-002 latest entry:")
table = ddb.Table('SankatMitra-LocationHistory-v2')
from boto3.dynamodb.conditions import Key
resp = table.query(
    KeyConditionExpression=Key('vehicleId').eq('AMB-IND-002'),
    ScanIndexForward=False, Limit=1
)
items = resp.get('Items', [])
if items:
    item = items[0]
    print(f"  lat={item.get('latitude')} lon={item.get('longitude')} ts={item.get('timestamp','?')[:20]}")
else:
    print("  No items found for AMB-IND-002")

# 3. Test the actual HTTP endpoint without auth
print("\nTest GET /corridor/corridors via HTTP (no auth):")
api = 'https://r0bh4n62b6.execute-api.ap-south-1.amazonaws.com/prod/corridor/corridors'
r = requests.get(api, timeout=5)
print(f"  HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  Corridors: {data.get('count',0)}")
    for c in data.get('corridors', []):
        print(f"    ID={c.get('corridorId','?')[:20]} ambLat={c.get('ambulanceLat','N/A')}")
else:
    print(f"  Body: {r.text[:200]}")
