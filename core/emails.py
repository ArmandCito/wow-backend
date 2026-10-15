"""
Emails sent by the API, in English or French (the `lang` the website sends with the request).
Plain text on purpose: readable everywhere, nothing to maintain in HTML.
"""

from django.conf import settings
from django.core.mail import send_mail

from .errors import EmailUnavailable

TEMPLATES = {
    "signup_code": {
        "en": (
            "Your WOW Quick Bites code: {code}",
            "Hello {name},\n\nYour verification code is:\n\n    {code}\n\n"
            "It expires in {minutes} minutes. If you did not create an account, ignore this email.\n\n"
            "WOW Quick Bites",
        ),
        "fr": (
            "Votre code WOW Quick Bites : {code}",
            "Bonjour {name},\n\nVotre code de vérification est :\n\n    {code}\n\n"
            "Il expire dans {minutes} minutes. Si vous n’avez pas créé de compte, ignorez cet email.\n\n"
            "WOW Quick Bites",
        ),
    },
    "password_reset": {
        "en": (
            "Reset your WOW Quick Bites password",
            "Hello {name},\n\nOpen this link to choose a new password (valid {minutes} minutes):\n\n{link}\n\n"
            "If you did not ask for it, ignore this email: your password stays the same.\n\nWOW Quick Bites",
        ),
        "fr": (
            "Réinitialisez votre mot de passe WOW Quick Bites",
            "Bonjour {name},\n\nOuvrez ce lien pour choisir un nouveau mot de passe (valable {minutes} minutes) :\n\n"
            "{link}\n\nSi vous n’êtes pas à l’origine de cette demande, ignorez cet email : votre mot de passe "
            "reste inchangé.\n\nWOW Quick Bites",
        ),
    },
    "staff_invitation": {
        "en": (
            "You are invited to the WOW Quick Bites portal",
            "Hello {name},\n\n{inviter} invited you to manage orders on the WOW Quick Bites portal.\n\n"
            "Open this link to choose your password (valid {days} days):\n\n{link}\n\nWOW Quick Bites",
        ),
        "fr": (
            "Invitation au portail WOW Quick Bites",
            "Bonjour {name},\n\n{inviter} vous invite à gérer les commandes sur le portail WOW Quick Bites.\n\n"
            "Ouvrez ce lien pour choisir votre mot de passe (valable {days} jours) :\n\n{link}\n\nWOW Quick Bites",
        ),
    },
}


def send(template, to, lang="en", **values):
    """Sends a templated email; raises EmailUnavailable (503) when the provider fails."""
    subject, body = TEMPLATES[template][lang if lang in ("en", "fr") else "en"]
    try:
        send_mail(subject.format(**values), body.format(**values), settings.DEFAULT_FROM_EMAIL, [to])
    except Exception as exc:
        raise EmailUnavailable() from exc


def frontend_link(lang, path, **query):
    """Absolute link to a page of the website: frontend_link("fr", "/forgot-password", token="…")."""
    from urllib.parse import urlencode

    lang = lang if lang in ("en", "fr") else "en"
    suffix = f"?{urlencode(query)}" if query else ""
    return f"{settings.FRONTEND_URL}/{lang}{path}{suffix}"
