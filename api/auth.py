import hmac
import os

from fastapi import Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(...)) -> None:
    """FastAPI dependency — validates X-API-Key header using constant-time comparison."""
    expected = os.environ["API_KEY"]
    if not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
