import boto3, os
from dotenv import load_dotenv
load_dotenv()
ddb = boto3.resource('dynamodb', region_name='ap-south-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

table = ddb.Table('SankatMitra-LocationHistory-v2')
resp = table.scan(ProjectionExpression='vehicleId,vehicleType,fcmToken', Limit=20)
items = resp.get('Items', [])
print(f'Items in LocationHistory: {len(items)}')
for item in items:
    ftoken = str(item.get('fcmToken',''))[:25] if item.get('fcmToken') else 'NONE'
    vtype = item.get('vehicleType', 'N/A')
    vid = item.get('vehicleId', 'N/A')
    print(f'  {vid} | type={vtype} | fcm={ftoken}...')
