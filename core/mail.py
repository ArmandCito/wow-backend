"""
Django email backend for the Brevo transactional API (https://api.brevo.com/v3/smtp/email).

Enabled by settings when BREVO_API_KEY is set, so the code only ever calls Django's `send_mail()`;
tests use Django's in-memory backend and development prints emails in the console.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                logger.exception("Brevo could not send the email to %s", message.to)
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, message):
        payload = {
            "sender": {"name": settings.EMAIL_SENDER_NAME, "email": settings.DEFAULT_FROM_EMAIL},
            "to": [{"email": address} for address in message.to],
            "subject": message.subject,
            "textContent": message.body,
        }
        html = next((content for content, mime in getattr(message, "alternatives", []) if mime == "text/html"), None)
        if html:
            payload["htmlContent"] = html

        request = urllib.request.Request(
            BREVO_URL,
            data=json.dumps(payload).encode(),
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": settings.BREVO_API_KEY,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status not in (200, 201, 202):
                    raise RuntimeError(f"Brevo answered HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Brevo rejected the email (HTTP {exc.code}): {body}") from exc
