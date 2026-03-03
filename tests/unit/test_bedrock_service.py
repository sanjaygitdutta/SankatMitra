import pytest
from unittest.mock import MagicMock, patch
import json
from backend.shared.bedrock_service import BedrockService

@pytest.fixture
def mock_bedrock_client():
    with patch("boto3.client") as mock_client:
        yield mock_client.return_value

def test_generate_multilingual_alert_fallback(mock_bedrock_client):
    # Test fallback when bedrock is disabled
    with patch("backend.shared.bedrock_service.get_settings") as mock_settings:
        mock_settings.return_value.bedrock_enabled = False
        service = BedrockService()
        alerts = service.generate_multilingual_alert("RIGHT", 120)
        
        assert "en" in alerts
        assert "hi" in alerts
        assert "bn" in alerts
        assert "right" in alerts["en"].lower()

def test_generate_multilingual_alert_success(mock_bedrock_client):
    # Mock successful Bedrock response
    mock_response = {
        "body": MagicMock()
    }
    mock_response["body"].read.return_value = json.dumps({
        "content": [
            {
                "text": json.dumps({
                    "en": "Ambulance coming, move right!",
                    "hi": "एंबुलेंस आ रही है, दाएं हटें!",
                    "bn": "অ্যাম্বুলেন্স আসছে, ডানে সরুন!"
                })
            }
        ]
    }).encode("utf-8")
    
    mock_bedrock_client.invoke_model.return_value = mock_response
    
    with patch("backend.shared.bedrock_service.get_settings") as mock_settings:
        mock_settings.return_value.bedrock_enabled = True
        mock_settings.return_value.bedrock_model_id = "test-model"
        
        service = BedrockService()
        alerts = service.generate_multilingual_alert("RIGHT", 120)
        
        assert alerts["en"] == "Ambulance coming, move right!"
        assert "एंबुलेंस" in alerts["hi"]
        assert "অ্যাম্বুলেন্স" in alerts["bn"]
