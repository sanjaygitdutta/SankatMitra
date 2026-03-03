import pytest
from backend.shared.config import get_settings

@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear the LRU cache for get_settings before each test to prevent state leakage."""
    get_settings.cache_clear()
    yield
