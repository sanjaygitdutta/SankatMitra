import boto3
import os
from datetime import datetime
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
TABLE_NAME = os.getenv("DYNAMO_VEHICLE_TABLE", "SankatMitra-VehicleRegistration-v2")

# Initialize DynamoDB Client
dynamodb = boto3.resource(
    'dynamodb',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

def seed_data():
    table = dynamodb.Table(TABLE_NAME)
    
    # Check if table exists, if not create it (basic version)
    try:
        table.table_status
    except Exception:
        print(f"Table {TABLE_NAME} not found. Creating...")
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{'AttributeName': 'vehicleId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'vehicleId', 'AttributeType': 'S'}],
            ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
        )
        table.wait_until_exists()

    # Data to seed
    ambulances = [
        {
            'vehicleId': 'AMB-IND-001',
            'registrationNumber': 'MH-01-AB-1234',
            'agencyId': 'AGENCY-MUM-01',
            'agencyName': 'Mumbai Central EMS',
            'state': 'Maharashtra',
            'district': 'Mumbai',
            'registeredAt': datetime.utcnow().isoformat(),
            'status': 'ACTIVE',
            'vehicleType': 'AMBULANCE'
        },
        {
            'vehicleId': 'AMB-IND-002',
            'registrationNumber': 'DL-01-CD-5678',
            'agencyId': 'AGENCY-DEL-02',
            'agencyName': 'Delhi Apollo Care',
            'state': 'Delhi',
            'district': 'New Delhi',
            'registeredAt': datetime.utcnow().isoformat(),
            'status': 'ACTIVE',
            'vehicleType': 'AMBULANCE'
        },
        {
            'vehicleId': 'AMB-IND-003',
            'registrationNumber': 'KA-01-EF-9012',
            'agencyId': 'AGENCY-BLR-03',
            'agencyName': 'Bangalore Fortis',
            'state': 'Karnataka',
            'district': 'Bengaluru',
            'registeredAt': datetime.utcnow().isoformat(),
            'status': 'ACTIVE',
            'vehicleType': 'AMBULANCE'
        }
    ]

    print(f"Seeding {len(ambulances)} vehicles into {TABLE_NAME}...")
    for amb in ambulances:
        table.put_item(Item=amb)
        print(f"✅ Seeded: {amb['vehicleId']} ({amb['agencyName']})")

if __name__ == "__main__":
    seed_data()
