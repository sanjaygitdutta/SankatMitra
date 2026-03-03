import json
import logging
import boto3
from typing import Dict, Optional
from .config import get_settings

logger = logging.getLogger(__name__)

class BedrockService:
    def __init__(self):
        self.settings = get_settings()
        self.client = boto3.client("bedrock-runtime", region_name=self.settings.aws_region)
        self.model_id = self.settings.bedrock_model_id

    def generate_multilingual_alert(self, direction: str, eta_seconds: int) -> Dict[str, str]:
        """
        Generate emergency alerts in English, Hindi, and Bengali using Amazon Bedrock.
        """
        if not self.settings.bedrock_enabled:
            return self._get_fallback_alerts(direction, eta_seconds)

        prompt = (
            f"Generate a concise emergency alert for a civilian vehicle to clear the path for an ambulance. "
            f"Direction: {direction.replace('_', ' ')}. ETA: {eta_seconds} seconds. "
            f"Provide the output as a JSON object with keys 'en', 'hi', and 'bn' for English, Hindi, and Bengali respectively. "
            f"Ensure the tone is urgent yet calm."
        )

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body
            )
            response_body = json.loads(response.get("body").read())
            content = response_body.get("content", [])[0].get("text", "")
            
            # Extract JSON from the response potentially containing markdown markers
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            alerts = json.loads(content)
            return alerts
        except Exception as e:
            logger.error(f"Error calling Bedrock: {e}")
            return self._get_fallback_alerts(direction, eta_seconds)

    def _get_fallback_alerts(self, direction: str, eta_seconds: int) -> Dict[str, str]:
        dir_friendly = direction.lower().replace("_", " ")
        return {
            "en": f"Emergency vehicle approaching. Please move {dir_friendly}. ETA: {eta_seconds}s.",
            "hi": f"आपातकालीन वाहन आ रहा है। कृपया {dir_friendly} की ओर हटें। ईटीए: {eta_seconds} सेकंड।",
            "bn": f"জরুরি গাড়ি আসছে। দয়া করে {dir_friendly}-এ সরে যান। ইটিএ: {eta_seconds} সেকেন্ড।"
        }

_service = None

def get_bedrock_service() -> BedrockService:
    global _service
    if _service is None:
        _service = BedrockService()
    return _service
