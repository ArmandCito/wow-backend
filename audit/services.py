from .models import AuditEvent


def record(*, actor, scope, type, text, values=None, target=None, data=None):
    """
    Records one audit event.

        record(actor=user, scope="orders", type="order.transition", data={...},
               text=("{order} moved to {stage}", "{order} passée à l’étape {stage}"),
               values={"order": "ORD-1042", "stage": {"en": "Preparing", "fr": "En préparation"}})

    `text` is an (English, French) pair of templates; a value given as {"en", "fr"} is picked per language.
    `actor=None` means the system (e.g. an order placed by a guest).
    """
    values = values or {}

    def render(template, lang):
        return template.format(**{k: v[lang] if isinstance(v, dict) else v for k, v in values.items()})[:300]

    return AuditEvent.objects.create(
        actor=actor,
        scope=scope,
        type=type,
        target=target,
        data=data or {},
        text_en=render(text[0], "en"),
        text_fr=render(text[1], "fr"),
    )
