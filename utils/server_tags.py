"""Fonctions indépendantes de discord.py pour comparer les tags de serveur."""


def normalize_server_tag(tag: str) -> str:
    """Normalise un tag sans modifier son alphabet ou ses caractères Unicode."""
    return tag.strip().casefold()


def get_primary_guild_identity(user) -> tuple[str | None, int | None]:
    """Retourne ``(tag_normalisé, serveur_source)`` pour un utilisateur."""
    primary_guild = getattr(user, "primary_guild", None)
    if primary_guild is None or getattr(primary_guild, "identity_enabled", None) is not True:
        return None, None

    tag = getattr(primary_guild, "tag", None)
    if not tag:
        return None, getattr(primary_guild, "id", None)
    return normalize_server_tag(tag), getattr(primary_guild, "id", None)


def user_matches_server_tag(user, tag_key: str, source_guild_id: int = 0) -> bool:
    """Vérifie le texte du tag et, si demandé, son serveur d'origine exact."""
    current_tag, current_guild_id = get_primary_guild_identity(user)
    if current_tag != tag_key:
        return False
    return not source_guild_id or current_guild_id == source_guild_id
