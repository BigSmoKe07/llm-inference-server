import pytest
import asyncio
from fastapi import HTTPException
from api.auth import verify_api_key


def test_valid_api_key_passes():
    asyncio.run(verify_api_key(x_api_key="test-key-abc123"))


def test_wrong_api_key_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_api_key(x_api_key="wrong-key"))
    assert exc_info.value.status_code == 401
