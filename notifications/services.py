"""
Client notifications, worded like the website (i18n/dictionaries/*/client-area.ts → notifications.templates).
"""

from core.time import rwf

from .models import ClientNotification

TEMPLATES = {
    "new": {
        "en": ("Order received", "Your order {id} was received."),
        "fr": ("Commande reçue", "Votre commande {id} a été reçue."),
    },
    "accepted": {
        "en": ("Your order was accepted", "{manager} accepted your order. Payment is due on pickup."),
        "fr": ("Votre commande a été acceptée", "{manager} a accepté votre commande. Le paiement est à effectuer au retrait."),
    },
    "preparing": {
        "en": ("Your order is being prepared", "{manager} started preparing {items}."),
        "fr": ("Votre commande est en préparation", "{manager} a commencé à préparer {items}."),
    },
    "ready": {
        "en": ("Your order is ready for pickup", "{manager} marked {items} ready. Come and collect it."),
        "fr": ("Votre commande est prête à retirer", "{manager} a indiqué que {items} est prêt. Venez le retirer."),
    },
    "completed": {
        "en": ("Pickup confirmed — order completed", "{items} collected. {total} was paid on pickup."),
        "fr": ("Retrait confirmé — commande terminée", "{items} retiré. {total} ont été payés au retrait."),
    },
    "cancelled": {
        "en": ("Your order was cancelled", "Your order was cancelled before preparation and was not charged."),
        "fr": ("Votre commande a été annulée", "Votre commande a été annulée avant sa préparation et n’a pas été facturée."),
    },
}


def items_summary(order, lang):
    """"WOW Toasted Burger + 2 × Fresh Mint Mojito" """
    return " + ".join(
        (f"{line.quantity} × " if line.quantity > 1 else "") + getattr(line, f"name_{lang}")
        for line in order.lines.all()
    )


def notify_stage(order):
    """Creates the notification of the order's current stage (account orders only: guests have no inbox)."""
    if order.client_id is None:
        return None
    values = {lang: {
        "id": order.public_id,
        "manager": order.manager.name if order.manager else "WOW Quick Bites",
        "items": items_summary(order, lang),
        "total": rwf(order.total),
    } for lang in ("en", "fr")}
    texts = {lang: [part.format(**values[lang]) for part in TEMPLATES[order.stage][lang]] for lang in ("en", "fr")}
    return ClientNotification.objects.create(
        client_id=order.client_id,
        order=order,
        stage=order.stage,
        title_en=texts["en"][0],
        title_fr=texts["fr"][0],
        text_en=texts["en"][1][:400],
        text_fr=texts["fr"][1][:400],
    )
