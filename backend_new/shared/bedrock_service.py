"""
SankatMitra – Amazon Bedrock Service Wrapper
Generates multilingual emergency instructions.
"""
import json
import boto3
from typing import Dict
from shared.config import get_settings

class BedrockService:
    def __init__(self):
        settings = get_settings()
        self.model_id = settings.bedrock_model_id
        self.bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def generate_multilingual_alert(self, direction: str, eta_seconds: int) -> Dict[str, str]:
        prompt = (
            f"Generate a very short, urgent emergency clear-path instruction for a vehicle. "
            f"The instruction is: 'Emergency vehicle approaching! Move to the {direction}. ETA {eta_seconds} seconds.' "
            f"Provide the instruction in 3 languages: English, Hindi, and Bengali. "
            f"Output ONLY a JSON object with keys 'en', 'hi', and 'bn'."
        )
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        })

        try:
            response = self.bedrock.invoke_model(body=body, modelId=self.model_id)
            resp_body = json.loads(response.get("body").read())
            text = resp_body["content"][0]["text"]
            # Extract JSON from potential Markdown or noise
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except Exception:
            # Fallback in case of API failure
            return {
                "en": f"Emergency approaching! Move {direction.lower()} now.",
                "hi": f"आपातकालीन वाहन आ रहा है! {direction.lower()} की ओर मुड़ें।",
                "bn": f"জরুরি গাড়ি আসছে! {direction.lower()} দিকে সরুন।"
            }

_instance = None
def get_bedrock_service():
    global _instance
    if _instance is None:
        _instance = BedrockService()
    return _instance
