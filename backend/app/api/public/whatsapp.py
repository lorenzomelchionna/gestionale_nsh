"""
Inbound WhatsApp webhook.

Twilio POSTs here whenever a client writes to the salon's number. The endpoint
is unauthenticated by necessity — Twilio cannot hold our credentials — so every
request is checked against the Twilio signature before anything is stored.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.chat import record_inbound
from app.utils.twilio_webhook import is_valid_twilio_request

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# Twilio treats any 2xx as delivered and stops retrying. An empty TwiML document
# is the documented way to say "received, nothing to send back".
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    if not is_valid_twilio_request(request, params):
        # 403 without detail: an attacker probing the endpoint learns nothing.
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    from_phone = params.get("From", "")
    body = params.get("Body", "")
    sid = params.get("MessageSid") or params.get("SmsMessageSid")
    profile_name = params.get("ProfileName")

    if from_phone and body:
        await record_inbound(
            db,
            from_phone=from_phone,
            body=body,
            provider_sid=sid,
            contact_name=profile_name,
        )

    return Response(content=EMPTY_TWIML, media_type="application/xml")
