"""
Validation for incoming Twilio webhooks.

The webhook endpoint has to be publicly reachable, so the signature is the only
thing separating a real inbound message from anyone posting a forged one. Twilio
signs the exact request URL concatenated with the POST parameters sorted by key,
using the account auth token as the HMAC-SHA1 secret.
"""
import base64
import hashlib
import hmac

from fastapi import Request

from app.config import settings


def expected_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    payload = url
    for key in sorted(params):
        payload += key + params[key]
    digest = hmac.new(
        auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def public_url(request: Request) -> str:
    """
    Rebuild the URL exactly as Twilio saw it.

    Railway terminates TLS at its edge and forwards over http, so `request.url`
    reports the wrong scheme and the signature would never match. Trust the
    forwarded headers to restore what the caller actually requested.
    """
    url = request.url
    proto = request.headers.get("x-forwarded-proto", url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or url.netloc
    rebuilt = f"{proto}://{host}{url.path}"
    if url.query:
        rebuilt += f"?{url.query}"
    return rebuilt


def is_valid_twilio_request(request: Request, params: dict[str, str]) -> bool:
    """
    True when the request carries a signature matching our auth token.

    Returns False when no auth token is configured: without the shared secret
    there is nothing to verify against, and accepting the request anyway would
    leave the endpoint open to anyone.
    """
    auth_token = settings.TWILIO_AUTH_TOKEN
    if not auth_token:
        return False

    signature = request.headers.get("x-twilio-signature")
    if not signature:
        return False

    candidate = expected_signature(public_url(request), params, auth_token)
    return hmac.compare_digest(candidate, signature)
