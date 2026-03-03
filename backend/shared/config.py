"""
SankatMitra – Configuration (reads from environment variables / .env)
"""
import os
from functools import lru_cache


class Settings:
    # AWS
    aws_region: str = os.getenv("AWS_REGION", "ap-south-1")

    # JWT
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expiry_hours: int = int(os.getenv("JWT_EXPIRY_HOURS", "1"))

    # DynamoDB
    dynamo_vehicle_table: str = os.getenv("DYNAMO_VEHICLE_TABLE", "SankatMitra-VehicleRegistration")
    dynamo_location_table: str = os.getenv("DYNAMO_LOCATION_TABLE", "SankatMitra-LocationHistory")
    dynamo_corridor_table: str = os.getenv("DYNAMO_CORRIDOR_TABLE", "SankatMitra-CorridorState")
    dynamo_alert_table: str = os.getenv("DYNAMO_ALERT_TABLE", "SankatMitra-AlertLog")

    # PostgreSQL
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "sankatmitra")
    postgres_user: str = os.getenv("POSTGRES_USER", "sankatmitra_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")

    # ElastiCache Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))

    # SageMaker
    sagemaker_endpoint_name: str = os.getenv(
        "SAGEMAKER_ENDPOINT_NAME", "sankatmitra-rnn-route-predictor"
    )

    # SNS
    sns_alert_topic_arn: str = os.getenv("SNS_ALERT_TOPIC_ARN", "")
    sns_spoofing_topic_arn: str = os.getenv("SNS_SPOOFING_TOPIC_ARN", "")

    # Firebase
    firebase_server_key: str = os.getenv("FIREBASE_SERVER_KEY", "")
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "sankatmitra-firebase")

    # Government EMS DB
    gov_db_api_url: str = os.getenv("GOV_DB_API_URL", "https://ems.gov.in/api/v1")
    gov_db_api_key: str = os.getenv("GOV_DB_API_KEY", "")

    # Alert / physics config
    alert_radius_meters: float = float(os.getenv("ALERT_RADIUS_METERS", "500"))
    max_speed_kmph: float = float(os.getenv("MAX_SPEED_KMPH", "150"))
    max_accel_ms2: float = float(os.getenv("MAX_ACCEL_MS2", "5.0"))
    gps_confidence_threshold: float = float(os.getenv("GPS_CONFIDENCE_THRESHOLD", "0.95"))
    corridor_timeout_minutes: int = int(os.getenv("CORRIDOR_TIMEOUT_MINUTES", "10"))
    route_cache_ttl_seconds: int = int(os.getenv("ROUTE_CACHE_TTL_SECONDS", "30"))
    auth_cache_ttl_minutes: int = int(os.getenv("AUTH_CACHE_TTL_MINUTES", "5"))

    # Bedrock
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    bedrock_enabled: bool = os.getenv("BEDROCK_ENABLED", "true").lower() == "true"

    # Auth retry
    auth_max_retries: int = 3
    auth_retry_delays: list = [1, 2, 4]  # seconds

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "development")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
