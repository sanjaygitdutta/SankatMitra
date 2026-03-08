"""
SankatMitra – Configuration
Version: 2.0.0-ForcedRedeploy
"""
import os
from functools import lru_cache

class Settings:
    def __init__(self):
        # AWS
        self.aws_region = os.environ.get("AWS_REGION", "ap-south-1")
        
        # DynamoDB
        self.dynamo_location_table = os.environ.get("DYNAMO_LOCATION_TABLE", "SankatMitra-LocationHistory-v2")
        self.dynamo_alert_table = os.environ.get("DYNAMO_ALERT_TABLE", "SankatMitra-Alerts-v2")
        self.dynamo_corridor_table = os.environ.get("DYNAMO_CORRIDOR_TABLE", "SankatMitra-Corridors-v2")
        self.dynamo_vehicle_table = os.environ.get("DYNAMO_VEHICLE_TABLE", "SankatMitra-Vehicles-v2")
        
        # Gov DB (Simulated)
        self.gov_db_api_url = os.environ.get("GOV_DB_API_URL", "https://api.gov.mock/v1")
        self.gov_db_api_key = os.environ.get("GOV_DB_API_KEY", "DEMO_KEY")

        # SNS
        self.sns_spoofing_topic_arn = os.environ.get("SNS_SPOOFING_TOPIC_ARN")
        
        # Bedrock
        self.bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        
        # Firebase
        self.firebase_server_key = os.environ.get("FIREBASE_SERVER_KEY", "")
        
        # App Logic
        self.alert_radius_meters = float(os.environ.get("ALERT_RADIUS_METERS", "500.0"))
        self.max_speed_kmph = float(os.environ.get("MAX_SPEED_KMPH", "120.0"))
        self.gps_confidence_threshold = float(os.environ.get("GPS_CONFIDENCE_THRESHOLD", "0.80"))
        
        self.environment = os.environ.get("ENVIRONMENT", "production")

@lru_cache()
def get_settings():
    return Settings()
