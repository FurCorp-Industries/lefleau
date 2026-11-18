"""Contrôles communs pour les rôles attribués automatiquement par le bot."""

import discord


def role_assign_problem(
    guild: discord.Guild,
    role: discord.Role,
    member: discord.Member | None = None,
    privileged: bool = False,
) -> str | None:
    """Retourne un message d'erreur si le bot ne peut pas (ou ne doit pas) attribuer ce rôle.

    `member` est la personne qui configure le rôle ; `privileged` la dispense de la
    vérification de hiérarchie (propriétaire du serveur, propriétaire du bot).
    """
    me = guild.me
    if role.is_default():
        return "Le rôle `@everyone` ne peut pas être utilisé."
    if role.managed:
        return "Ce rôle est géré par Discord ou une intégration."
    if me is None or not me.guild_permissions.manage_roles:
        return "Le bot doit posséder la permission **Gérer les rôles**."
    if role >= me.top_role:
        return "Le rôle choisi doit être placé sous le rôle le plus élevé du bot."
    if not privileged and member is not None and role >= member.top_role:
        return "Tu ne peux pas configurer un rôle égal ou supérieur à ton rôle principal."
    return None
