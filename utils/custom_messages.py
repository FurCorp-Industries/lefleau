"""Validation des options des messages personnalisés."""

DEFAULT_MESSAGE_COLOR = 0x5865F2


def parse_embed_color(raw_color: str) -> int | None:
    """Convertit #RRGGBB en entier Discord. Une valeur vide prend le bleu Discord."""
    value = raw_color.strip()
    if not value:
        return DEFAULT_MESSAGE_COLOR
    if value.startswith("#"):
        value = value[1:]
    if len(value) != 6:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def is_valid_image_url(url: str) -> bool:
    """Évite les valeurs manifestement invalides avant de les donner à Discord."""
    value = url.strip()
    return not value or value.startswith("https://") or value.startswith("http://")
