"""Alert delivery.

Real SMS/email needs a provider account and credentials that don't exist yet
(Twilio for SMS, SMTP/SendGrid for email), so delivery is stubbed - it logs
what *would* be sent, behind the same call shape a real integration would
use. To go live: set the relevant _ENABLED flag and fill in send_email /
send_sms's body with an actual API call. Nothing else in the alert pipeline
needs to change.
"""
import logging

log = logging.getLogger("notifier")

EMAIL_ENABLED = False
SMS_ENABLED = False

DEFAULT_EMAIL_RECIPIENT = "ops-team@example.com"
DEFAULT_SMS_RECIPIENT = "+15555550100"

_CONDITION_SYMBOLS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def _format_message(event) -> str:
    symbol = _CONDITION_SYMBOLS.get(event.condition, event.condition)
    return (
        f"[{event.severity.upper()}] {event.device_instance_id} / {event.tag_key} "
        f"{symbol} {event.threshold} (current value: {event.value})"
    )


def send_email(event, to_address: str = DEFAULT_EMAIL_RECIPIENT):
    message = _format_message(event)
    if not EMAIL_ENABLED:
        log.info("[STUB EMAIL -> %s] %s", to_address, message)
        return
    raise NotImplementedError("Wire up SMTP/SendGrid here once credentials are configured")


def send_sms(event, to_number: str = DEFAULT_SMS_RECIPIENT):
    message = _format_message(event)
    if not SMS_ENABLED:
        log.info("[STUB SMS -> %s] %s", to_number, message)
        return
    raise NotImplementedError("Wire up Twilio (or similar) here once credentials are configured")


def notify(event):
    """Called once per new breach (not per reading) - see mqtt_ingest._evaluate_alerts."""
    send_email(event)
    send_sms(event)
