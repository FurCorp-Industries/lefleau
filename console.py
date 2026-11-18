"""
console.py
------------
Panel de contrôle en ligne de commande. Tourne dans le même terminal que
le bot (démarré automatiquement par bot.py), dans un thread séparé, pour
pouvoir administrer le bot sans passer par Discord : stats, gestion des
joueurs, état des boss, etc.

Fonctionne en tapant des commandes après le prompt "bot> ", pendant que
le bot continue de tourner normalement en tâche de fond.
"""

import asyncio
import threading

from rich.console import Console
from rich.table import Table

import database as db
from utils.helpers import format_berrys

rich_console = Console()

STOP_COMMANDS = {"stop", "quit", "exit"}


class AdminConsole:
    """Console d'administration tournant dans un thread séparé du bot."""

    def __init__(self, bot, loop: asyncio.AbstractEventLoop):
        self.bot = bot
        self.loop = loop
        self._thread: threading.Thread | None = None

    def start(self):
        """Démarre la console dans un thread démon (s'arrête automatiquement avec le bot)."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        rich_console.print(
            "\n[bold cyan]🏴‍☠️ Panel de contrôle actif — tape 'help' pour la liste des commandes[/bold cyan]\n"
        )
        while True:
            try:
                raw = input("bot> ").strip()
            except (EOFError, KeyboardInterrupt):
                rich_console.print("\n[yellow]Console fermée (le bot continue de tourner).[/yellow]")
                return

            if not raw:
                continue

            parts = raw.split()
            command = parts[0].lower()
            args = parts[1:]

            try:
                self._dispatch(command, args)
            except Exception as e:
                rich_console.print(f"[red]Erreur : {e}[/red]")

            if command in STOP_COMMANDS:
                rich_console.print("[yellow]Console arrêtée.[/yellow]")
                return

    def _dispatch(self, command: str, args: list[str]):
        handler = COMMANDS.get(command)
        if handler is None:
            rich_console.print(f"[red]Commande inconnue : '{command}'. Tape 'help' pour la liste.[/red]")
            return

        # On est dans un thread séparé de la boucle asyncio du bot : on
        # planifie donc la coroutine sur cette boucle, et on attend son
        # résultat de façon synchrone (safe, ce n'est pas la boucle elle-même).
        future = asyncio.run_coroutine_threadsafe(handler(self.bot, args), self.loop)
        future.result()


# ------------------------------------------------------------------
# Commandes disponibles
# ------------------------------------------------------------------

async def cmd_help(bot, args):
    table = Table(title="📖 Commandes disponibles")
    table.add_column("Commande", style="cyan")
    table.add_column("Description")

    rows = [
        ("help", "Affiche cette aide"),
        ("stats", "Statistiques globales de l'économie (tous serveurs)"),
        ("guilds", "Liste des serveurs où le bot est présent"),
        ("boss", "État du boss actuel de chaque serveur"),
        ("give <user_id> <guild_id> <montant>", "Ajoute des Berrys à un joueur"),
        ("remove <user_id> <guild_id> <montant>", "Retire des Berrys à un joueur"),
        ("reset <user_id> <guild_id>", "Réinitialise complètement un joueur"),
        ("broadcast <channel_id> <message>", "Envoie un message dans un salon précis"),
        ("clear", "Efface l'écran du terminal"),
        ("stop", "Arrête proprement le bot (alias: quit, exit)"),
    ]
    for cmd, desc in rows:
        table.add_row(cmd, desc)

    rich_console.print(table)


async def cmd_stats(bot, args):
    stats = await db.get_global_stats()

    table = Table(title="📊 Statistiques globales")
    table.add_column("Métrique")
    table.add_column("Valeur", justify="right")

    table.add_row("Joueurs enregistrés", str(stats["user_count"]))
    table.add_row("Berrys en circulation", format_berrys(stats["total_wallet"]))
    table.add_row("Prime totale cumulée", format_berrys(stats["total_bounty"]))
    table.add_row("Fruits du Démon possédés", str(stats["fruits_owned"]))
    table.add_row("Serveurs connectés", str(len(bot.guilds)))

    rich_console.print(table)


async def cmd_guilds(bot, args):
    table = Table(title="🌐 Serveurs connectés")
    table.add_column("Nom")
    table.add_column("ID")
    table.add_column("Membres", justify="right")

    for guild in bot.guilds:
        table.add_row(guild.name, str(guild.id), str(guild.member_count))

    rich_console.print(table)


async def cmd_boss(bot, args):
    table = Table(title="👹 Boss actuels")
    table.add_column("Serveur")
    table.add_column("Boss")
    table.add_column("PV", justify="right")

    for guild in bot.guilds:
        boss = await db.get_boss(guild.id)
        if boss is None:
            table.add_row(guild.name, "(aucun combat lancé)", "-")
        else:
            table.add_row(guild.name, boss["name"], f"{boss['current_hp']}/{boss['max_hp']}")

    rich_console.print(table)


async def cmd_give(bot, args):
    if len(args) != 3:
        rich_console.print("[red]Usage : give <user_id> <guild_id> <montant>[/red]")
        return
    user_id, guild_id, amount = int(args[0]), int(args[1]), int(args[2])
    new_balance = await db.update_wallet(user_id, guild_id, amount)
    rich_console.print(f"[green]✅ {format_berrys(amount)} ajoutés. Nouveau solde : {format_berrys(new_balance)}[/green]")


async def cmd_remove(bot, args):
    if len(args) != 3:
        rich_console.print("[red]Usage : remove <user_id> <guild_id> <montant>[/red]")
        return
    user_id, guild_id, amount = int(args[0]), int(args[1]), int(args[2])
    new_balance = await db.update_wallet(user_id, guild_id, -amount)
    rich_console.print(f"[green]✅ {format_berrys(amount)} retirés. Nouveau solde : {format_berrys(new_balance)}[/green]")


async def cmd_reset(bot, args):
    if len(args) != 2:
        rich_console.print("[red]Usage : reset <user_id> <guild_id>[/red]")
        return
    user_id, guild_id = int(args[0]), int(args[1])
    await db.reset_user(user_id, guild_id)
    rich_console.print(f"[green]✅ Joueur {user_id} réinitialisé sur le serveur {guild_id}.[/green]")


async def cmd_broadcast(bot, args):
    if len(args) < 2:
        rich_console.print("[red]Usage : broadcast <channel_id> <message>[/red]")
        return
    channel_id = int(args[0])
    message = " ".join(args[1:])

    channel = bot.get_channel(channel_id)
    if channel is None:
        rich_console.print(f"[red]Salon {channel_id} introuvable (le bot y a-t-il accès ?).[/red]")
        return

    await channel.send(message)
    rich_console.print(f"[green]✅ Message envoyé dans #{channel.name}.[/green]")


async def cmd_stop(bot, args):
    rich_console.print("[yellow]Arrêt du bot en cours...[/yellow]")
    await bot.close()


async def cmd_clear(bot, args):
    rich_console.clear()


COMMANDS = {
    "help": cmd_help,
    "stats": cmd_stats,
    "guilds": cmd_guilds,
    "boss": cmd_boss,
    "give": cmd_give,
    "remove": cmd_remove,
    "reset": cmd_reset,
    "broadcast": cmd_broadcast,
    "stop": cmd_stop,
    "quit": cmd_stop,
    "exit": cmd_stop,
    "clear": cmd_clear,
}
