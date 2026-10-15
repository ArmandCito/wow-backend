"""
Rate limiting per visitor.

The website calls the API from its server, so every request comes from the website's IP. The
website forwards the visitor's IP in `X-Client-IP`, trusted only with the shared secret header
`X-Frontend-Secret` (settings.FRONTEND_SHARED_SECRET). Other callers are limited by their own IP.
"""

import hmac

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


def from_website(request):
    secret = settings.FRONTEND_SHARED_SECRET
    sent = request.headers.get("X-Frontend-Secret", "")
    return bool(secret) and hmac.compare_digest(sent, secret)


class VisitorRateThrottle(ScopedRateThrottle):
    """Set `throttle_scope = "sign_in"` (see REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]) on the view."""

    def get_ident(self, request):
        if from_website(request) and request.headers.get("X-Client-IP"):
            return request.headers["X-Client-IP"].strip()[:64]
        return super().get_ident(request)

    def get_cache_key(self, request, view):
        # Always per visitor (not per account): these endpoints are used before signing in
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
