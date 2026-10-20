"""HMAC SHA-256 Webhook Verification Utility.

Guarantees cryptographic origin verification for incoming external payment webhooks.
"""

import hashlib
import hmac


def generate_webhook_signature(payload: bytes, secret: str) -> str:
    """Generates an HMAC SHA-256 hexadecimal signature for the given payload."""
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Performs constant-time HMAC SHA-256 signature verification preventing timing attacks."""
    if not signature or not secret:
        return False

    expected_sig = generate_webhook_signature(payload, secret)
    # Strip optional sha256= prefix if sent by providers like GitHub / Stripe
    clean_sig = signature.removeprefix("sha256=")
    return hmac.compare_digest(clean_sig, expected_sig)
