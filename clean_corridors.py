import boto3, os
from dotenv import load_dotenv
load_dotenv()

ddb = boto3.resource('dynamodb', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

table = ddb.Table('SankatMitra-CorridorState-v2')
resp = table.scan()
items = resp.get('Items', [])
print(f"Total corridors: {len(items)}")

# Keep only the most recent active corridor, mark old ones as COMPLETED
from datetime import datetime, timezone

active = [i for i in items if i.get('status') == 'ACTIVE']
print(f"Active corridors: {len(active)}")

active_sorted = sorted(active, key=lambda x: x.get('createdAt',''), reverse=True)
to_close = active_sorted[1:]  # Keep newest, close all others

for c in to_close:
    cid = c.get('corridorId')
    print(f"Closing stale: {cid[:20]}")
    table.update_item(
        Key={'corridorId': cid},
        UpdateExpression='SET #s = :done, updatedAt = :ts',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':done': 'COMPLETED',
            ':ts': datetime.now(timezone.utc).isoformat()
        }
    )

# Show remaining active
resp2 = table.scan(FilterExpression=boto3.dynamodb.conditions.Attr('status').eq('ACTIVE'))
remaining = resp2.get('Items', [])
print(f"\nRemaining active corridors: {len(remaining)}")
for c in remaining:
    print(f"  ID={c.get('corridorId','?')[:30]}")
    print(f"  vehicle={c.get('emergencyVehicleId','?')}")
    print(f"  created={c.get('createdAt','?')}")
