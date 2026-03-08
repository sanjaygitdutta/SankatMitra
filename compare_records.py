import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv()

dynamodb = boto3.resource(
    'dynamodb',
    region_name=os.getenv("AWS_REGION", "ap-south-1"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

table = dynamodb.Table(os.getenv("DYNAMO_VEHICLE_TABLE", "SankatMitra-VehicleRegistration-v2"))

def get_record(vid):
    resp = table.get_item(Key={'vehicleId': vid})
    return resp.get('Item')

print("AMB-IND-001:", json.dumps(get_record("AMB-IND-001"), indent=2))
print("AMB-IND-002:", json.dumps(get_record("AMB-IND-002"), indent=2))
