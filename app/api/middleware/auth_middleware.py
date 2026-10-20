"""Merchant API Key Authentication & Scoped Authorization Middleware."""

from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Configurable valid merchant API keys mapping key -> tenant_id
DEFAULT_API_KEYS: dict[str, str] = {
    "sk_live_merchant_default": "default",
    "sk_live_merchant_alpha": "tenant_alpha",
    "sk_test_mock_sandbox": "sandbox",
}


async def get_current_tenant(
    api_key: Annotated[str | None, Security(API_KEY_HEADER)] = None,
) -> str:
    """Validates the merchant API key and resolves the calling tenant identity."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-API-Key header.",
        )

    tenant_id = DEFAULT_API_KEYS.get(api_key)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or unauthorized API key.",
        )

    return tenant_id
