"""Unit and integration tests for Security, Auth, and Webhook Verification.

Verifies:
1. Merchant API key validation and scoped tenant authorization.
2. Distributed tracing correlation ID extraction and response header propagation.
3. HMAC SHA-256 signature verification preventing webhook forgery and replay attacks.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.auth_middleware import get_current_tenant
from app.api.middleware.correlation_middleware import (
    CorrelationIdMiddleware,
    get_correlation_id,
)
from app.api.security.webhook_verifier import (
    generate_webhook_signature,
    verify_webhook_signature,
)

# Test application isolating security components
app = FastAPI()
app.add_middleware(CorrelationIdMiddleware)


@app.get("/secure/tenant")
async def secure_tenant_endpoint(tenant: str = Depends(get_current_tenant)) -> dict[str, str]:
    return {"tenant_id": tenant, "correlation_id": get_correlation_id()}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestSecurityAndAuth:
    """Verifies authentication, correlation headers, and webhook crypto checks."""

    def test_missing_api_key_returns_401(self, client: TestClient) -> None:
        response = client.get("/secure/tenant")
        assert response.status_code == 401
        assert "Missing required X-API-Key" in response.json()["detail"]

    def test_invalid_api_key_returns_403(self, client: TestClient) -> None:
        response = client.get(
            "/secure/tenant",
            headers={"X-API-Key": "sk_invalid_unauthorized_token"},
        )
        assert response.status_code == 403
        assert "Invalid or unauthorized API key" in response.json()["detail"]

    def test_valid_api_key_authenticates_tenant(self, client: TestClient) -> None:
        response = client.get(
            "/secure/tenant",
            headers={"X-API-Key": "sk_live_merchant_alpha"},
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] == "tenant_alpha"

    def test_correlation_id_propagated_and_returned(self, client: TestClient) -> None:
        custom_cid = "cid_test_trace_778899"
        response = client.get(
            "/secure/tenant",
            headers={
                "X-API-Key": "sk_live_merchant_default",
                "X-Correlation-ID": custom_cid,
            },
        )
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == custom_cid
        assert response.json()["correlation_id"] == custom_cid

    def test_auto_generated_correlation_id_when_missing(self, client: TestClient) -> None:
        response = client.get(
            "/secure/tenant",
            headers={"X-API-Key": "sk_live_merchant_default"},
        )
        assert response.status_code == 200
        generated_cid = response.headers.get("X-Correlation-ID")
        assert generated_cid is not None
        assert generated_cid.startswith("cid_")

    def test_webhook_hmac_sha256_verification(self) -> None:
        secret = "super_secret_webhook_signing_key_12345"
        payload = b'{"event": "payout.succeeded", "amount": "500.00", "currency": "USD"}'

        # Valid signature
        signature = generate_webhook_signature(payload, secret)
        assert verify_webhook_signature(payload, signature, secret) is True
        # Accepts sha256= prefix as standard
        assert verify_webhook_signature(payload, f"sha256={signature}", secret) is True

        # Tampered payload
        tampered_payload = b'{"event": "payout.succeeded", "amount": "9999.00", "currency": "USD"}'
        assert verify_webhook_signature(tampered_payload, signature, secret) is False

        # Wrong secret
        assert verify_webhook_signature(payload, signature, "wrong_secret") is False

        # Empty credentials
        assert verify_webhook_signature(payload, "", secret) is False
        assert verify_webhook_signature(payload, signature, "") is False
