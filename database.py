"""
database.py
------------
Toute la logique d'accès à la base SQLite passe par ce module.
On utilise aiosqlite pour rester 100% asynchrone (compatible avec
la boucle d'événements de discord.py).

Tables :
- users      : solde, prime (bounty), fruit équipé, timestamps de cooldown
- inventory  : fruits du démon possédés par chaque joueur
"""

import aiosqlite
from datetime import datetime, timezone

import config

# --- Requêtes de création des tables ---

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    wallet INTEGER NOT NULL DEFAULT 500,
    bounty INTEGER NOT NULL DEFAULT 0,
    equipped_fruit TEXT DEFAULT NULL,
    last_daily TEXT DEFAULT NULL,
    last_work TEXT DEFAULT NULL,
    last_crime TEXT DEFAULT NULL,
    PRIMARY KEY (user_id, guild_id)
);
"""

CREATE_INVENTORY_TABLE = """
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    fruit_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    UNIQUE(user_id, guild_id, fruit_id)
);
"""

CREATE_BOSSES_TABLE = """
CREATE TABLE IF NOT EXISTS bosses (
    guild_id INTEGER PRIMARY KEY,
    boss_index INTEGER NOT NULL DEFAULT 0,
    current_hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    name TEXT NOT NULL
);
"""

CREATE_BOSS_DAMAGE_TABLE = """
CREATE TABLE IF NOT EXISTS boss_damage (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
"""

CREATE_MATERIALS_TABLE = """
CREATE TABLE IF NOT EXISTS materials (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    material_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id, material_id)
);
"""

CREATE_TICKET_CATEGORIES_TABLE = """
CREATE TABLE IF NOT EXISTS ticket_categories (
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    discord_category_id INTEGER NOT NULL,
    role_id INTEGER,
    message TEXT NOT NULL,
    PRIMARY KEY (guild_id, name)
);
"""

CREATE_TICKET_CATEGORY_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS ticket_category_roles (
    guild_id INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, category_name, role_id)
);
"""

CREATE_TICKETS_TABLE = """
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    claimed_by INTEGER,
    claimed_at TEXT
);
"""

CREATE_TICKET_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS ticket_settings (
    guild_id INTEGER PRIMARY KEY,
    log_channel_id INTEGER
);
"""

CREATE_TRACKED_TICKETS_TABLE = """
CREATE TABLE IF NOT EXISTS tracked_tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    status_channel_id INTEGER NOT NULL,
    status_message_id INTEGER NOT NULL,
    tracked_by INTEGER NOT NULL,
    tracked_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'attente'
);
"""

CREATE_WARNINGS_TABLE = """
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

CREATE_LOG_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS log_settings (
    guild_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, category)
);
"""

CREATE_LOCKED_CHANNELS_TABLE = """
CREATE TABLE IF NOT EXISTS locked_channels (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    previous_send_messages INTEGER,
    locked_by INTEGER NOT NULL,
    locked_at TEXT NOT NULL
);
"""

CREATE_BLOXFRUITS_PROFILES_TABLE = """
CREATE TABLE IF NOT EXISTS blox_fruits_profiles (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    bounty TEXT NOT NULL,
    build TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, guild_id)
);
"""

CREATE_GIVEAWAYS_TABLE = """
CREATE TABLE IF NOT EXISTS giveaways (
    message_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    prize TEXT NOT NULL,
    winner_count INTEGER NOT NULL DEFAULT 1,
    ends_at TEXT NOT NULL,
    required_role_id INTEGER,
    bypass_role_id INTEGER,
    min_account_age_seconds INTEGER NOT NULL DEFAULT 0,
    min_membership_seconds INTEGER NOT NULL DEFAULT 0,
    host_id INTEGER NOT NULL,
    ended INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_GIVEAWAY_ENTRIES_TABLE = """
CREATE TABLE IF NOT EXISTS giveaway_entries (
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    entered_at TEXT NOT NULL,
    PRIMARY KEY (message_id, user_id)
);
"""

CREATE_GIVEAWAY_PRIZE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS giveaway_prize_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    name_key TEXT NOT NULL,
    points INTEGER NOT NULL CHECK(points > 0),
    emoji TEXT NOT NULL DEFAULT '🎁',
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(guild_id, name_key)
);
"""

CREATE_GIVEAWAY_POINT_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS giveaway_point_settings (
    guild_id INTEGER PRIMARY KEY,
    points_name TEXT NOT NULL DEFAULT 'Points'
);
"""

CREATE_GIVEAWAY_MEMBER_POINTS_TABLE = """
CREATE TABLE IF NOT EXISTS giveaway_member_points (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 0 CHECK(points >= 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
"""

CREATE_GIVEAWAY_POINT_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS giveaway_point_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    points_required INTEGER NOT NULL CHECK(points_required > 0),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);
"""

CREATE_GIVEAWAY_POINT_AWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS giveaway_point_awards (
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    points INTEGER NOT NULL CHECK(points > 0),
    awarded_at TEXT NOT NULL,
    PRIMARY KEY (message_id, user_id)
);
"""

CREATE_GIVEAWAY_PROPOSALS_TABLE = """
CREATE TABLE IF NOT EXISTS giveaway_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    ticket_channel_id INTEGER NOT NULL,
    proposer_id INTEGER NOT NULL,
    prize_item_id INTEGER,
    prize_name TEXT NOT NULL,
    prize_points INTEGER NOT NULL CHECK(prize_points > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'denied')),
    created_at TEXT NOT NULL,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    log_channel_id INTEGER,
    log_message_id INTEGER,
    status_message_id INTEGER,
    duration_seconds INTEGER,
    target_channel_id INTEGER,
    winner_count INTEGER NOT NULL DEFAULT 1,
    required_role_id INTEGER,
    bypass_role_id INTEGER,
    min_account_age_seconds INTEGER NOT NULL DEFAULT 0,
    min_membership_seconds INTEGER NOT NULL DEFAULT 0,
    published_message_id INTEGER
);
"""

CREATE_ANTIRAID_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS antiraid_settings (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    join_threshold INTEGER NOT NULL DEFAULT 6,
    window_seconds INTEGER NOT NULL DEFAULT 10,
    min_account_age_seconds INTEGER NOT NULL DEFAULT 604800,
    log_channel_id INTEGER,
    bypass_role_id INTEGER
);
"""

CREATE_SANCTION_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS sanction_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    sanction_type TEXT NOT NULL,
    moderator_id INTEGER,
    moderator_name TEXT,
    reason TEXT NOT NULL,
    duration_seconds INTEGER,
    created_at TEXT NOT NULL
);
"""

CREATE_SANCTION_LOG_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS sanction_log_settings (
    source_guild_id INTEGER PRIMARY KEY,
    destination_guild_id INTEGER NOT NULL,
    destination_channel_id INTEGER NOT NULL
);
"""

CREATE_ROBLOX_LINKS_TABLE = """
CREATE TABLE IF NOT EXISTS roblox_links (
    discord_user_id INTEGER PRIMARY KEY,
    roblox_user_id INTEGER NOT NULL UNIQUE,
    roblox_username TEXT NOT NULL,
    roblox_display_name TEXT NOT NULL,
    profile_url TEXT,
    picture_url TEXT,
    roblox_created_at INTEGER,
    linked_at TEXT NOT NULL,
    last_guild_id INTEGER
);
"""

CREATE_ROBLOX_OAUTH_STATES_TABLE = """
CREATE TABLE IF NOT EXISTS roblox_oauth_states (
    state TEXT PRIMARY KEY,
    discord_user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    code_verifier TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""

CREATE_MESSAGE_EDITOR_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS panel_message_editor_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);
"""

CREATE_PANEL_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS panel_messages (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    message_type TEXT NOT NULL CHECK(message_type IN ('text', 'embed')),
    content TEXT NOT NULL DEFAULT '',
    embed_title TEXT NOT NULL DEFAULT '',
    embed_description TEXT NOT NULL DEFAULT '',
    embed_color TEXT NOT NULL DEFAULT '#5865F2',
    embed_footer TEXT NOT NULL DEFAULT '',
    embed_image TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL,
    updated_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, message_id)
);
"""

CREATE_PANEL_ACCESS_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS panel_access_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);
"""

CREATE_CUSTOM_SHOP_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS custom_shop_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    name_key TEXT NOT NULL,
    description TEXT NOT NULL,
    price INTEGER NOT NULL CHECK(price > 0),
    emoji TEXT NOT NULL DEFAULT '📦',
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(guild_id, name),
    UNIQUE(guild_id, name_key)
);
"""

CREATE_CUSTOM_INVENTORY_TABLE = """
CREATE TABLE IF NOT EXISTS custom_inventory (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
    acquired_at TEXT NOT NULL,
    PRIMARY KEY (user_id, guild_id, item_id),
    FOREIGN KEY (item_id) REFERENCES custom_shop_items(id)
);
"""

CREATE_GLOBAL_BLACKLIST_TABLE = """
CREATE TABLE IF NOT EXISTS global_blacklist (
    user_id INTEGER PRIMARY KEY,
    reason TEXT NOT NULL,
    added_by INTEGER NOT NULL,
    added_at TEXT NOT NULL
);
"""

CREATE_SERVER_TAG_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS server_tag_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    tag_key TEXT NOT NULL,
    source_guild_id INTEGER NOT NULL DEFAULT 0,
    role_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(guild_id, tag_key, source_guild_id, role_id)
);
"""

CREATE_JOIN_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS join_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    target TEXT NOT NULL DEFAULT 'all' CHECK(target IN ('all', 'humans', 'bots')),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);
"""

CREATE_JOIN_ROLE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS join_role_settings (
    guild_id INTEGER PRIMARY KEY,
    wait_screening INTEGER NOT NULL DEFAULT 1
);
"""

CREATE_SERVER_TAG_ASSIGNMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS server_tag_assignments (
    rule_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (rule_id, user_id),
    FOREIGN KEY (rule_id) REFERENCES server_tag_rules(id) ON DELETE CASCADE
);
"""


CREATE_REACTION_ROLE_PANELS_TABLE = """
CREATE TABLE IF NOT EXISTS reaction_role_panels (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, message_id)
);
"""

CREATE_REACTION_ROLE_MAPPINGS_TABLE = """
CREATE TABLE IF NOT EXISTS reaction_role_mappings (
    guild_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    emoji_key TEXT NOT NULL,
    emoji_display TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, message_id, emoji_key),
    FOREIGN KEY (guild_id, message_id) REFERENCES reaction_role_panels(guild_id, message_id) ON DELETE CASCADE
);
"""

# --- Profils et résultats RYUKAI ---
# Les informations de profil sont propres à chaque serveur : un même membre
# peut jouer dans des équipes différentes selon la communauté.
CREATE_RYUKAI_PROFILES_TABLE = """
CREATE TABLE IF NOT EXISTS ryukai_profiles (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    team TEXT NOT NULL DEFAULT '—',
    rank_name TEXT NOT NULL DEFAULT '—',
    platform TEXT NOT NULL DEFAULT 'PC / CONSOLE',
    region TEXT NOT NULL DEFAULT '—',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
"""

CREATE_RYUKAI_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS ryukai_stats (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    war_wins INTEGER NOT NULL DEFAULT 0 CHECK(war_wins >= 0),
    war_losses INTEGER NOT NULL DEFAULT 0 CHECK(war_losses >= 0),
    pub_war_wins INTEGER NOT NULL DEFAULT 0 CHECK(pub_war_wins >= 0),
    pub_war_losses INTEGER NOT NULL DEFAULT 0 CHECK(pub_war_losses >= 0),
    duel_wins INTEGER NOT NULL DEFAULT 0 CHECK(duel_wins >= 0),
    duel_losses INTEGER NOT NULL DEFAULT 0 CHECK(duel_losses >= 0),
    PRIMARY KEY (guild_id, user_id)
);
"""

CREATE_RYUKAI_WAR_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS ryukai_war_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    match_type TEXT NOT NULL CHECK(match_type IN ('war', 'pub_war', 'duel')),
    recorded_by INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
"""

CREATE_RYUKAI_WAR_PARTICIPANTS_TABLE = """
CREATE TABLE IF NOT EXISTS ryukai_war_participants (
    result_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('win', 'loss')),
    PRIMARY KEY (result_id, user_id),
    FOREIGN KEY (result_id) REFERENCES ryukai_war_results(id) ON DELETE CASCADE
);
"""

async def _column_exists(db, table: str, column: str) -> bool:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in await cursor.fetchall()]
    return column in columns


async def init_db():
    """Initialise la base de données (création des tables + migrations si besoin)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(CREATE_USERS_TABLE)
        await db.execute(CREATE_INVENTORY_TABLE)
        await db.execute(CREATE_BOSSES_TABLE)
        await db.execute(CREATE_BOSS_DAMAGE_TABLE)
        await db.execute(CREATE_MATERIALS_TABLE)
        await db.execute(CREATE_TICKET_CATEGORIES_TABLE)
        await db.execute(CREATE_TICKET_CATEGORY_ROLES_TABLE)
        await db.execute(CREATE_TICKETS_TABLE)
        await db.execute(CREATE_TICKET_SETTINGS_TABLE)
        await db.execute(CREATE_TRACKED_TICKETS_TABLE)
        await db.execute(CREATE_WARNINGS_TABLE)
        await db.execute(CREATE_LOG_SETTINGS_TABLE)
        await db.execute(CREATE_LOCKED_CHANNELS_TABLE)
        await db.execute(CREATE_BLOXFRUITS_PROFILES_TABLE)
        await db.execute(CREATE_GIVEAWAYS_TABLE)
        await db.execute(CREATE_GIVEAWAY_ENTRIES_TABLE)
        await db.execute(CREATE_GIVEAWAY_PRIZE_ITEMS_TABLE)
        await db.execute(CREATE_GIVEAWAY_POINT_SETTINGS_TABLE)
        await db.execute(CREATE_GIVEAWAY_MEMBER_POINTS_TABLE)
        await db.execute(CREATE_GIVEAWAY_POINT_ROLES_TABLE)
        await db.execute(CREATE_GIVEAWAY_POINT_AWARDS_TABLE)
        await db.execute(CREATE_GIVEAWAY_PROPOSALS_TABLE)
        await db.execute(CREATE_JOIN_ROLES_TABLE)
        await db.execute(CREATE_JOIN_ROLE_SETTINGS_TABLE)
        await db.execute(CREATE_ANTIRAID_SETTINGS_TABLE)
        await db.execute(CREATE_SANCTION_RECORDS_TABLE)
        await db.execute(CREATE_SANCTION_LOG_SETTINGS_TABLE)
        await db.execute(CREATE_ROBLOX_LINKS_TABLE)
        await db.execute(CREATE_ROBLOX_OAUTH_STATES_TABLE)
        await db.execute(CREATE_PANEL_ACCESS_ROLES_TABLE)
        await db.execute(CREATE_MESSAGE_EDITOR_ROLES_TABLE)
        await db.execute(CREATE_PANEL_MESSAGES_TABLE)
        await db.execute(CREATE_REACTION_ROLE_PANELS_TABLE)
        await db.execute(CREATE_REACTION_ROLE_MAPPINGS_TABLE)
        await db.execute(CREATE_RYUKAI_PROFILES_TABLE)
        await db.execute(CREATE_RYUKAI_STATS_TABLE)
        await db.execute(CREATE_RYUKAI_WAR_RESULTS_TABLE)
        await db.execute(CREATE_RYUKAI_WAR_PARTICIPANTS_TABLE)
        await db.execute(CREATE_CUSTOM_SHOP_ITEMS_TABLE)
        await db.execute(CREATE_CUSTOM_INVENTORY_TABLE)
        await db.execute(CREATE_GLOBAL_BLACKLIST_TABLE)
        await db.execute(CREATE_SERVER_TAG_RULES_TABLE)
        await db.execute(CREATE_SERVER_TAG_ASSIGNMENTS_TABLE)

        # Les premières versions de la boutique ne possédaient pas de clé
        # Unicode normalisée. ``casefold`` permet de traiter correctement les
        # noms accentués (par exemple « Clé » et « CLÉ »).
        if not await _column_exists(db, "custom_shop_items", "name_key"):
            await db.execute("ALTER TABLE custom_shop_items ADD COLUMN name_key TEXT")
            rows = await (await db.execute(
                "SELECT id, guild_id, name FROM custom_shop_items ORDER BY id"
            )).fetchall()
            seen: dict[tuple[int, str], int] = {}
            for item_id, guild_id, name in rows:
                name_key = name.casefold()
                duplicate_of = seen.get((guild_id, name_key))
                if duplicate_of is None:
                    seen[(guild_id, name_key)] = item_id
                    await db.execute(
                        "UPDATE custom_shop_items SET name_key = ? WHERE id = ?",
                        (name_key, item_id),
                    )
                    continue
                inventories = await (await db.execute(
                    "SELECT user_id, guild_id, quantity, acquired_at FROM custom_inventory WHERE item_id = ?",
                    (item_id,),
                )).fetchall()
                for user_id, inventory_guild_id, quantity, acquired_at in inventories:
                    await db.execute(
                        "INSERT INTO custom_inventory (user_id, guild_id, item_id, quantity, acquired_at) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, guild_id, item_id) DO UPDATE SET "
                        "quantity = quantity + excluded.quantity, acquired_at = excluded.acquired_at",
                        (user_id, inventory_guild_id, duplicate_of, quantity, acquired_at),
                    )
                await db.execute("DELETE FROM custom_inventory WHERE item_id = ?", (item_id,))
                await db.execute("DELETE FROM custom_shop_items WHERE id = ?", (item_id,))
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_shop_guild_name_key "
            "ON custom_shop_items(guild_id, name_key)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_custom_shop_guild_active "
            "ON custom_shop_items(guild_id, active, name)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_server_tag_rules_guild "
            "ON server_tag_rules(guild_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_giveaway_prize_items_guild_active "
            "ON giveaway_prize_items(guild_id, active, name)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_giveaway_member_points_guild "
            "ON giveaway_member_points(guild_id, points DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_giveaway_proposals_guild_status "
            "ON giveaway_proposals(guild_id, status, created_at DESC)"
        )
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_giveaway_proposal_pending_ticket "
            "ON giveaway_proposals(ticket_channel_id) WHERE status = 'pending'"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ryukai_results_guild_created "
            "ON ryukai_war_results(guild_id, recorded_at DESC)"
        )
        await db.execute("PRAGMA optimize")
        await db.commit()

        # Migrations : ajoute les colonnes manquantes sans effacer les
        # données existantes des joueurs, pour les bases créées avant
        # l'ajout du système de boss / des quêtes / du multi-équipement.
        if not await _column_exists(db, "users", "last_attack"):
            await db.execute("ALTER TABLE users ADD COLUMN last_attack TEXT DEFAULT NULL")

        if not await _column_exists(db, "giveaways", "prize_item_id"):
            await db.execute("ALTER TABLE giveaways ADD COLUMN prize_item_id INTEGER DEFAULT NULL")
        if not await _column_exists(db, "giveaways", "prize_points"):
            await db.execute("ALTER TABLE giveaways ADD COLUMN prize_points INTEGER NOT NULL DEFAULT 0")
        if not await _column_exists(db, "users", "last_quest"):
            await db.execute("ALTER TABLE users ADD COLUMN last_quest TEXT DEFAULT NULL")
        if not await _column_exists(db, "inventory", "level"):
            await db.execute("ALTER TABLE inventory ADD COLUMN level INTEGER NOT NULL DEFAULT 1")

        if not await _column_exists(db, "users", "multi_fruit_unlocked"):
            await db.execute("ALTER TABLE users ADD COLUMN multi_fruit_unlocked INTEGER NOT NULL DEFAULT 0")

        if not await _column_exists(db, "ticket_categories", "emoji"):
            await db.execute("ALTER TABLE ticket_categories ADD COLUMN emoji TEXT DEFAULT NULL")

        if not await _column_exists(db, "giveaway_proposals", "status_message_id"):
            await db.execute("ALTER TABLE giveaway_proposals ADD COLUMN status_message_id INTEGER DEFAULT NULL")
        # Paramètres de publication automatique des propositions (migration sans perte).
        for col, definition in {
            "duration_seconds": "INTEGER", "target_channel_id": "INTEGER",
            "winner_count": "INTEGER NOT NULL DEFAULT 1", "required_role_id": "INTEGER",
            "bypass_role_id": "INTEGER", "min_account_age_seconds": "INTEGER NOT NULL DEFAULT 0",
            "min_membership_seconds": "INTEGER NOT NULL DEFAULT 0", "published_message_id": "INTEGER",
        }.items():
            if not await _column_exists(db, "giveaway_proposals", col):
                await db.execute(f"ALTER TABLE giveaway_proposals ADD COLUMN {col} {definition}")

        # Conserve automatiquement l'ancien rôle unique lors du passage au
        # système multi-rôles.
        await db.execute(
            "INSERT OR IGNORE INTO ticket_category_roles (guild_id, category_name, role_id) "
            "SELECT guild_id, name, role_id FROM ticket_categories WHERE role_id IS NOT NULL"
        )

        for column in ("fruit", "sword", "gun", "fighting_style"):
            if not await _column_exists(db, "blox_fruits_profiles", column):
                await db.execute(f"ALTER TABLE blox_fruits_profiles ADD COLUMN {column} TEXT DEFAULT NULL")

        if not await _column_exists(db, "ticket_settings", "tracking_channel_id"):
            await db.execute("ALTER TABLE ticket_settings ADD COLUMN tracking_channel_id INTEGER DEFAULT NULL")

        if not await _column_exists(db, "tickets", "claimed_by"):
            await db.execute("ALTER TABLE tickets ADD COLUMN claimed_by INTEGER DEFAULT NULL")
        if not await _column_exists(db, "tickets", "claimed_at"):
            await db.execute("ALTER TABLE tickets ADD COLUMN claimed_at TEXT DEFAULT NULL")
        if not await _column_exists(db, "tracked_tickets", "status"):
            await db.execute("ALTER TABLE tracked_tickets ADD COLUMN status TEXT NOT NULL DEFAULT 'attente'")

        needs_equipped_migration = not await _column_exists(db, "inventory", "equipped")
        if needs_equipped_migration:
            await db.execute("ALTER TABLE inventory ADD COLUMN equipped INTEGER NOT NULL DEFAULT 0")
            await db.commit()
            # Reporte l'ancien fruit équipé (users.equipped_fruit, système à
            # slot unique) vers le nouveau système (inventory.equipped),
            # pour ne pas déséquiper tout le monde lors de la mise à jour.
            await db.execute(
                "UPDATE inventory SET equipped = 1 "
                "WHERE (user_id, guild_id, fruit_id) IN ("
                "  SELECT user_id, guild_id, equipped_fruit FROM users "
                "  WHERE equipped_fruit IS NOT NULL"
                ")"
            )

        await db.commit()


async def get_panel_access_roles(guild_id: int) -> list[int]:
    """Retourne les rôles auxquels un administrateur a délégué l'accès au panel."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        rows = await (await db.execute(
            "SELECT role_id FROM panel_access_roles WHERE guild_id = ? ORDER BY role_id",
            (guild_id,),
        )).fetchall()
        return [row[0] for row in rows]


async def set_panel_access_roles(guild_id: int, role_ids: list[int]):
    """Remplace atomiquement les rôles autorisés à administrer le panel."""
    unique_ids = sorted(set(role_ids))
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("DELETE FROM panel_access_roles WHERE guild_id = ?", (guild_id,))
        await db.executemany(
            "INSERT INTO panel_access_roles (guild_id, role_id) VALUES (?, ?)",
            [(guild_id, role_id) for role_id in unique_ids],
        )
        await db.commit()


# --- Blacklist globale (panel Owner uniquement) ---

async def add_global_blacklist(user_id: int, reason: str, added_by: int) -> dict:
    """Ajoute ou met à jour un utilisateur dans la blacklist globale."""
    added_at = _now_iso()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO global_blacklist (user_id, reason, added_by, added_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "reason = excluded.reason, added_by = excluded.added_by, added_at = excluded.added_at",
            (user_id, reason, added_by, added_at),
        )
        await db.commit()
        row = await (await db.execute(
            "SELECT * FROM global_blacklist WHERE user_id = ?", (user_id,)
        )).fetchone()
        return dict(row)


async def remove_global_blacklist(user_id: int) -> bool:
    """Retire un utilisateur de la blacklist sans modifier les bans locaux."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM global_blacklist WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_global_blacklist_entry(user_id: int) -> dict | None:
    """Retourne une entrée de blacklist, ou None si l'ID n'est pas blacklisté."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM global_blacklist WHERE user_id = ?", (user_id,)
        )).fetchone()
        return dict(row) if row else None


async def get_global_blacklist() -> list[dict]:
    """Liste la blacklist globale, de l'ajout le plus récent au plus ancien."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM global_blacklist ORDER BY added_at DESC, user_id"
        )).fetchall()
        return [dict(row) for row in rows]


def _now_iso() -> str:
    """Retourne l'heure actuelle (UTC) au format ISO, pour stockage en base."""
    return datetime.now(timezone.utc).isoformat()


# --- Gestion des utilisateurs ---

async def get_user(user_id: int, guild_id: int) -> dict:
    """
    Récupère les données d'un utilisateur. Le crée automatiquement
    avec le solde de départ s'il n'existe pas encore.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        row = await cursor.fetchone()

        if row is None:
            await db.execute(
                "INSERT INTO users (user_id, guild_id, wallet) VALUES (?, ?, ?)",
                (user_id, guild_id, config.STARTING_WALLET),
            )
            await db.commit()
            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "wallet": config.STARTING_WALLET,
                "bounty": 0,
                "equipped_fruit": None,
                "multi_fruit_unlocked": 0,
                "last_daily": None,
                "last_work": None,
                "last_crime": None,
                "last_attack": None,
                "last_quest": None,
            }

        return dict(row)


async def update_wallet(user_id: int, guild_id: int, delta: int) -> int:
    """
    Ajoute (ou retire si delta est négatif) un montant au portefeuille.
    Le solde ne peut jamais descendre sous 0.
    Retourne le nouveau solde.
    """
    user = await get_user(user_id, guild_id)
    new_wallet = max(0, user["wallet"] + delta)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET wallet = ? WHERE user_id = ? AND guild_id = ?",
            (new_wallet, user_id, guild_id),
        )
        await db.commit()

    return new_wallet


async def update_bounty(user_id: int, guild_id: int, delta: int) -> int:
    """Ajoute un montant à la prime (bounty) du joueur. Ne descend jamais sous 0."""
    user = await get_user(user_id, guild_id)
    new_bounty = max(0, user["bounty"] + delta)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET bounty = ? WHERE user_id = ? AND guild_id = ?",
            (new_bounty, user_id, guild_id),
        )
        await db.commit()

    return new_bounty


async def set_cooldown(user_id: int, guild_id: int, field: str):
    """
    Met à jour le timestamp de cooldown pour une commande donnée.
    `field` doit être 'last_daily', 'last_work', 'last_crime', 'last_attack' ou 'last_quest'.
    """
    assert field in ("last_daily", "last_work", "last_crime", "last_attack", "last_quest")
    await get_user(user_id, guild_id)  # s'assure que la ligne existe

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE users SET {field} = ? WHERE user_id = ? AND guild_id = ?",
            (_now_iso(), user_id, guild_id),
        )
        await db.commit()


def get_cooldown_remaining(last_timestamp: str | None, cooldown_seconds: float) -> float:
    """
    Calcule le temps restant (en secondes) avant qu'un cooldown ne soit terminé.
    Retourne 0 si la commande est utilisable immédiatement.
    """
    if last_timestamp is None:
        return 0.0

    last_time = datetime.fromisoformat(last_timestamp)
    elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
    remaining = cooldown_seconds - elapsed
    return max(0.0, remaining)


# --- Gestion de l'inventaire (Fruits du Démon) ---

async def add_fruit_to_inventory(user_id: int, guild_id: int, fruit_id: str):
    """Ajoute un fruit à l'inventaire d'un joueur."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO inventory (user_id, guild_id, fruit_id, acquired_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, guild_id, fruit_id, _now_iso()),
        )
        await db.commit()


async def has_fruit(user_id: int, guild_id: int, fruit_id: str) -> bool:
    """Vérifie si un joueur possède déjà un fruit précis."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM inventory WHERE user_id = ? AND guild_id = ? AND fruit_id = ?",
            (user_id, guild_id, fruit_id),
        )
        return await cursor.fetchone() is not None


async def get_inventory(user_id: int, guild_id: int) -> list[str]:
    """Retourne la liste des identifiants de fruits possédés par le joueur."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT fruit_id FROM inventory WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def equip_fruit(user_id: int, guild_id: int, fruit_id: str):
    """
    Équipe (fait manger) un fruit.
    - Sans le passif Barbe Noire : un seul fruit actif à la fois (canon
      oblige : manger 2 fruits = mort !) — équiper un nouveau fruit
      déséquipe automatiquement l'ancien.
    - Avec le passif Barbe Noire débloqué (/barbenoire) : le fruit vient
      s'ajouter aux autres déjà actifs, sans limite.
    """
    await get_user(user_id, guild_id)
    has_passive = await has_multi_fruit_passive(user_id, guild_id)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        if not has_passive:
            await db.execute(
                "UPDATE inventory SET equipped = 0 WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
        await db.execute(
            "UPDATE inventory SET equipped = 1 "
            "WHERE user_id = ? AND guild_id = ? AND fruit_id = ?",
            (user_id, guild_id, fruit_id),
        )
        await db.commit()


async def unequip_fruit(user_id: int, guild_id: int, fruit_id: str | None = None):
    """
    Déséquipe un fruit précis (fruit_id fourni), ou TOUS les fruits actifs
    si fruit_id est None.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        if fruit_id is None:
            await db.execute(
                "UPDATE inventory SET equipped = 0 WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
        else:
            await db.execute(
                "UPDATE inventory SET equipped = 0 "
                "WHERE user_id = ? AND guild_id = ? AND fruit_id = ?",
                (user_id, guild_id, fruit_id),
            )
        await db.commit()


async def get_equipped_fruits(user_id: int, guild_id: int) -> list[str]:
    """Retourne la liste des identifiants de TOUS les fruits actuellement équipés."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT fruit_id FROM inventory WHERE user_id = ? AND guild_id = ? AND equipped = 1",
            (user_id, guild_id),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


# --- Passif spécial : Barbe Noire (multi-équipement illimité) ---

async def has_multi_fruit_passive(user_id: int, guild_id: int) -> bool:
    """Vérifie si le joueur a débloqué le passif Barbe Noire."""
    user = await get_user(user_id, guild_id)
    return bool(user.get("multi_fruit_unlocked", 0))


async def unlock_multi_fruit_passive(user_id: int, guild_id: int):
    """Débloque définitivement le passif Barbe Noire pour ce joueur."""
    await get_user(user_id, guild_id)
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET multi_fruit_unlocked = 1 WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await db.commit()


# --- Boutique personnalisée par serveur ---

async def upsert_custom_item(
    guild_id: int,
    name: str,
    description: str,
    price: int,
    emoji: str,
    created_by: int,
) -> dict:
    """Crée un objet de serveur ou met à jour/réactive celui portant le même nom."""
    now = _now_iso()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO custom_shop_items "
            "(guild_id, name, name_key, description, price, emoji, active, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?) "
            "ON CONFLICT(guild_id, name_key) DO UPDATE SET "
            "name = excluded.name, "
            "description = excluded.description, price = excluded.price, emoji = excluded.emoji, "
            "active = 1, created_by = excluded.created_by, updated_at = excluded.updated_at",
            (guild_id, name, name.casefold(), description, price, emoji, created_by, now, now),
        )
        await db.commit()
        row = await (await db.execute(
            "SELECT * FROM custom_shop_items WHERE guild_id = ? AND name_key = ?",
            (guild_id, name.casefold()),
        )).fetchone()
        return dict(row)


async def get_custom_items(guild_id: int, include_inactive: bool = False) -> list[dict]:
    """Retourne le catalogue personnalisé d'un serveur, trié par nom."""
    query = "SELECT * FROM custom_shop_items WHERE guild_id = ?"
    params: tuple = (guild_id,)
    if not include_inactive:
        query += " AND active = 1"
    query += " ORDER BY name COLLATE NOCASE"
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(query, params)).fetchall()
        return [dict(row) for row in rows]


async def get_custom_item(guild_id: int, name: str, include_inactive: bool = False) -> dict | None:
    """Cherche un objet par son nom, sans tenir compte des majuscules."""
    query = (
        "SELECT * FROM custom_shop_items "
        "WHERE guild_id = ? AND name_key = ?"
    )
    if not include_inactive:
        query += " AND active = 1"
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(query, (guild_id, name.casefold()))).fetchone()
        return dict(row) if row else None


async def disable_custom_item(guild_id: int, name: str) -> bool:
    """Retire un objet de la vente sans le supprimer des inventaires existants."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE custom_shop_items SET active = 0, updated_at = ? "
            "WHERE guild_id = ? AND name_key = ? AND active = 1",
            (_now_iso(), guild_id, name.casefold()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def set_custom_item_active(guild_id: int, name: str, active: bool) -> bool:
    """Active ou désactive un objet existant sans toucher aux inventaires."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE custom_shop_items SET active = ?, updated_at = ? "
            "WHERE guild_id = ? AND name_key = ?",
            (int(active), _now_iso(), guild_id, name.casefold()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def purchase_custom_item(user_id: int, guild_id: int, name: str, quantity: int) -> dict:
    """
    Achète une quantité d'objet dans une transaction unique.

    Le verrou d'écriture évite que deux achats simultanés utilisent le même
    solde. Retourne toujours un dictionnaire avec une clé ``status``.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, guild_id, wallet) VALUES (?, ?, ?)",
            (user_id, guild_id, config.STARTING_WALLET),
        )
        item_row = await (await db.execute(
            "SELECT * FROM custom_shop_items "
            "WHERE guild_id = ? AND name_key = ? AND active = 1",
            (guild_id, name.casefold()),
        )).fetchone()
        if item_row is None:
            await db.rollback()
            return {"status": "not_found"}

        item = dict(item_row)
        total = item["price"] * quantity
        wallet_row = await (await db.execute(
            "SELECT wallet FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )).fetchone()
        wallet = wallet_row["wallet"]
        if wallet < total:
            await db.rollback()
            return {"status": "insufficient_funds", "item": item, "total": total, "wallet": wallet}

        new_wallet = wallet - total
        now = _now_iso()
        await db.execute(
            "UPDATE users SET wallet = ? WHERE user_id = ? AND guild_id = ?",
            (new_wallet, user_id, guild_id),
        )
        await db.execute(
            "INSERT INTO custom_inventory (user_id, guild_id, item_id, quantity, acquired_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, guild_id, item_id) DO UPDATE SET "
            "quantity = quantity + excluded.quantity, acquired_at = excluded.acquired_at",
            (user_id, guild_id, item["id"], quantity, now),
        )
        quantity_row = await (await db.execute(
            "SELECT quantity FROM custom_inventory "
            "WHERE user_id = ? AND guild_id = ? AND item_id = ?",
            (user_id, guild_id, item["id"]),
        )).fetchone()
        await db.commit()
        return {
            "status": "ok",
            "item": item,
            "total": total,
            "wallet": new_wallet,
            "quantity_owned": quantity_row["quantity"],
        }


async def get_custom_inventory(user_id: int, guild_id: int) -> list[dict]:
    """Retourne les objets personnalisés possédés, y compris ceux retirés de la vente."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT i.quantity, i.acquired_at, s.name, s.description, s.price, s.emoji, s.active "
            "FROM custom_inventory AS i "
            "JOIN custom_shop_items AS s ON s.id = i.item_id "
            "WHERE i.user_id = ? AND i.guild_id = ? AND i.quantity > 0 "
            "ORDER BY s.name COLLATE NOCASE",
            (user_id, guild_id),
        )).fetchall()
        return [dict(row) for row in rows]


# --- Réinitialisation complète du compte ---

async def reset_user(user_id: int, guild_id: int):
    """
    Réinitialise entièrement les données d'un joueur sur ce serveur :
    - portefeuille remis au montant de départ
    - prime (bounty) remise à 0
    - fruit équipé retiré
    - passif Barbe Noire retiré (à racheter si voulu)
    - tous les cooldowns effacés
    - tout l'inventaire de Fruits du Démon supprimé
    - tout l'inventaire d'objets personnalisés supprimé
    """
    await get_user(user_id, guild_id)  # s'assure que la ligne existe

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET wallet = ?, bounty = 0, equipped_fruit = NULL, multi_fruit_unlocked = 0, "
            "last_daily = NULL, last_work = NULL, last_crime = NULL, last_attack = NULL, last_quest = NULL "
            "WHERE user_id = ? AND guild_id = ?",
            (config.STARTING_WALLET, user_id, guild_id),
        )
        await db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await db.execute(
            "DELETE FROM custom_inventory WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await db.commit()


# --- Gestion du Boss (combats communautaires) ---

async def get_boss(guild_id: int) -> dict | None:
    """Retourne l'état du boss actuel du serveur, ou None si aucun boss n'a jamais été créé."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM bosses WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_boss(guild_id: int, boss_index: int, name: str, max_hp: int):
    """Crée ou remplace le boss actuel d'un serveur (PV au maximum)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO bosses (guild_id, boss_index, current_hp, max_hp, name) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET boss_index = excluded.boss_index, "
            "current_hp = excluded.current_hp, max_hp = excluded.max_hp, name = excluded.name",
            (guild_id, boss_index, max_hp, max_hp, name),
        )
        await db.commit()


async def damage_boss(guild_id: int, amount: int) -> int:
    """Inflige des dégâts au boss du serveur. Retourne les PV restants (jamais sous 0)."""
    boss = await get_boss(guild_id)
    new_hp = max(0, boss["current_hp"] - amount)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE bosses SET current_hp = ? WHERE guild_id = ?",
            (new_hp, guild_id),
        )
        await db.commit()

    return new_hp


async def add_boss_damage(guild_id: int, user_id: int, amount: int):
    """Ajoute des dégâts au total cumulé d'un joueur sur le boss actuel (pour le partage du butin)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO boss_damage (guild_id, user_id, damage) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET damage = damage + excluded.damage",
            (guild_id, user_id, amount),
        )
        await db.commit()


async def get_boss_damage_ranking(guild_id: int) -> list[tuple[int, int]]:
    """Retourne [(user_id, degats), ...] triés du plus gros dégât au plus petit."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, damage FROM boss_damage WHERE guild_id = ? ORDER BY damage DESC",
            (guild_id,),
        )
        return await cursor.fetchall()


async def clear_boss_damage(guild_id: int):
    """Efface le tableau des dégâts infligés (à appeler après la mort d'un boss)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("DELETE FROM boss_damage WHERE guild_id = ?", (guild_id,))
        await db.commit()


# --- Statistiques globales (utilisées par le panel de contrôle en terminal) ---

async def get_global_stats() -> dict:
    """Retourne des statistiques agrégées sur toute la base (tous serveurs confondus)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(wallet), 0), COALESCE(SUM(bounty), 0) FROM users"
        )
        user_count, total_wallet, total_bounty = await cursor.fetchone()

        cursor2 = await db.execute("SELECT COUNT(*) FROM inventory")
        (fruits_owned,) = await cursor2.fetchone()

        custom_items_row = await (await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(active), 0) FROM custom_shop_items"
        )).fetchone()
        custom_owned_row = await (await db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM custom_inventory"
        )).fetchone()

        return {
            "user_count": user_count,
            "total_wallet": total_wallet,
            "total_bounty": total_bounty,
            "fruits_owned": fruits_owned,
            "custom_items": custom_items_row[0],
            "active_custom_items": custom_items_row[1],
            "custom_items_owned": custom_owned_row[0],
        }


async def get_guild_economy_stats(guild_id: int) -> dict:
    """Retourne les totaux économiques d'un seul serveur pour le panel web."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        row = await (await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(wallet), 0), COALESCE(SUM(bounty), 0) "
            "FROM users WHERE guild_id = ?",
            (guild_id,),
        )).fetchone()
        return {
            "user_count": row[0],
            "total_wallet": row[1],
            "total_bounty": row[2],
        }


# --- Matériaux (obtenus via /quest, dépensés via /enhance) ---

async def add_material(user_id: int, guild_id: int, material_id: str, amount: int = 1):
    """Ajoute (ou retire si amount négatif) une quantité d'un matériau à l'inventaire."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO materials (user_id, guild_id, material_id, quantity) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, guild_id, material_id) DO UPDATE SET quantity = quantity + excluded.quantity",
            (user_id, guild_id, material_id, amount),
        )
        await db.commit()


async def get_materials(user_id: int, guild_id: int) -> dict[str, int]:
    """Retourne {material_id: quantite} pour tous les matériaux possédés (quantité > 0)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT material_id, quantity FROM materials WHERE user_id = ? AND guild_id = ? AND quantity > 0",
            (user_id, guild_id),
        )
        rows = await cursor.fetchall()
        return {material_id: qty for material_id, qty in rows}


async def has_enough_materials(user_id: int, guild_id: int, required: dict[str, int]) -> bool:
    """Vérifie que le joueur possède au moins les quantités requises de chaque matériau."""
    owned = await get_materials(user_id, guild_id)
    return all(owned.get(material_id, 0) >= qty for material_id, qty in required.items())


async def spend_materials(user_id: int, guild_id: int, required: dict[str, int]):
    """Déduit les quantités de matériaux indiquées (à appeler après has_enough_materials)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        for material_id, qty in required.items():
            await db.execute(
                "UPDATE materials SET quantity = quantity - ? "
                "WHERE user_id = ? AND guild_id = ? AND material_id = ?",
                (qty, user_id, guild_id, material_id),
            )
        await db.commit()


# --- Niveaux de Fruits du Démon (améliorés via /enhance) ---

async def get_fruit_level(user_id: int, guild_id: int, fruit_id: str) -> int:
    """Retourne le niveau actuel d'un fruit possédé (1 si non trouvé/non amélioré)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT level FROM inventory WHERE user_id = ? AND guild_id = ? AND fruit_id = ?",
            (user_id, guild_id, fruit_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else 1


async def set_fruit_level(user_id: int, guild_id: int, fruit_id: str, level: int):
    """Définit le niveau d'un fruit possédé."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE inventory SET level = ? WHERE user_id = ? AND guild_id = ? AND fruit_id = ?",
            (level, user_id, guild_id, fruit_id),
        )
        await db.commit()

# --- Système de tickets (indépendant de l'économie) ---

class _Unset:
    """Sentinelle représentant 'ne pas modifier ce champ' (distincte de None, qui signifie 'effacer')."""

    def __repr__(self):
        return "UNSET"


UNSET = _Unset()


async def set_ticket_category(
    guild_id: int,
    name: str,
    discord_category_id: int,
    role_id: int | None,
    message: str,
    emoji: str | None = None,
    role_ids: list[int] | None = None,
):
    """Crée ou met à jour (en totalité) la configuration d'une catégorie de ticket."""
    name_key = name.strip().lower()
    configured_roles = list(dict.fromkeys(role_ids if role_ids is not None else ([role_id] if role_id else [])))
    legacy_role_id = configured_roles[0] if configured_roles else None
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "INSERT INTO ticket_categories "
            "(guild_id, name, display_name, discord_category_id, role_id, message, emoji) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET "
            "display_name = excluded.display_name, "
            "discord_category_id = excluded.discord_category_id, "
            "role_id = excluded.role_id, "
            "message = excluded.message, "
            "emoji = excluded.emoji",
            (guild_id, name_key, name.strip(), discord_category_id, legacy_role_id, message, emoji),
        )
        await db.execute(
            "DELETE FROM ticket_category_roles WHERE guild_id = ? AND category_name = ?",
            (guild_id, name_key),
        )
        await db.executemany(
            "INSERT INTO ticket_category_roles (guild_id, category_name, role_id) VALUES (?, ?, ?)",
            [(guild_id, name_key, configured_role_id) for configured_role_id in configured_roles],
        )
        await db.commit()


async def update_ticket_category(
    guild_id: int,
    name: str,
    discord_category_id=UNSET,
    role_id=UNSET,
    message=UNSET,
    emoji=UNSET,
    role_ids=UNSET,
) -> bool:
    """
    Met à jour UNIQUEMENT les champs fournis d'une catégorie de ticket
    existante (les champs laissés à UNSET ne sont pas touchés). Passer
    explicitement None pour un champ (role_id, emoji) l'efface.
    Retourne False si la catégorie n'existe pas.
    """
    current = await get_ticket_category(guild_id, name)
    if current is None:
        return False

    new_category_id = current["discord_category_id"] if discord_category_id is UNSET else discord_category_id
    if role_ids is not UNSET:
        new_role_ids = list(dict.fromkeys(role_ids))
    elif role_id is not UNSET:
        new_role_ids = [role_id] if role_id is not None else []
    else:
        new_role_ids = current.get("role_ids", [])
    new_role_id = new_role_ids[0] if new_role_ids else None
    new_message = current["message"] if message is UNSET else message
    new_emoji = current["emoji"] if emoji is UNSET else emoji

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "UPDATE ticket_categories SET discord_category_id = ?, role_id = ?, message = ?, emoji = ? "
            "WHERE guild_id = ? AND name = ?",
            (new_category_id, new_role_id, new_message, new_emoji, guild_id, name.strip().lower()),
        )
        if role_ids is not UNSET or role_id is not UNSET:
            name_key = name.strip().lower()
            await db.execute(
                "DELETE FROM ticket_category_roles WHERE guild_id = ? AND category_name = ?",
                (guild_id, name_key),
            )
            await db.executemany(
                "INSERT INTO ticket_category_roles (guild_id, category_name, role_id) VALUES (?, ?, ?)",
                [(guild_id, name_key, configured_role_id) for configured_role_id in new_role_ids],
            )
        await db.commit()
    return True


async def get_ticket_categories(guild_id: int) -> list[dict]:
    """Retourne toutes les catégories de ticket configurées pour ce serveur."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ticket_categories WHERE guild_id = ? ORDER BY display_name",
            (guild_id,),
        )
        rows = await cursor.fetchall()
        role_rows = await (await db.execute(
            "SELECT category_name, role_id FROM ticket_category_roles "
            "WHERE guild_id = ? ORDER BY category_name, role_id",
            (guild_id,),
        )).fetchall()
        roles_by_category: dict[str, list[int]] = {}
        for category_name, configured_role_id in role_rows:
            roles_by_category.setdefault(category_name, []).append(configured_role_id)
        categories = []
        for row in rows:
            category = dict(row)
            category["role_ids"] = roles_by_category.get(category["name"], [])
            categories.append(category)
        return categories


async def get_ticket_category(guild_id: int, name: str) -> dict | None:
    """Retourne la configuration d'une catégorie de ticket précise, ou None."""
    name_key = name.strip().lower()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND name = ?",
            (guild_id, name_key),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        category = dict(row)
        role_rows = await (await db.execute(
            "SELECT role_id FROM ticket_category_roles "
            "WHERE guild_id = ? AND category_name = ? ORDER BY role_id",
            (guild_id, name_key),
        )).fetchall()
        category["role_ids"] = [configured_role_id for (configured_role_id,) in role_rows]
        return category


async def remove_ticket_category(guild_id: int, name: str) -> bool:
    """Supprime une catégorie de ticket. Retourne True si elle existait."""
    name_key = name.strip().lower()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "DELETE FROM ticket_category_roles WHERE guild_id = ? AND category_name = ?",
            (guild_id, name_key),
        )
        cursor = await db.execute(
            "DELETE FROM ticket_categories WHERE guild_id = ? AND name = ?",
            (guild_id, name_key),
        )
        await db.commit()
        return cursor.rowcount > 0


async def create_ticket(channel_id: int, guild_id: int, user_id: int, category_name: str):
    """Enregistre un ticket ouvert."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, category_name, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel_id, guild_id, user_id, category_name.strip().lower(), _now_iso()),
        )
        await db.commit()


async def get_open_ticket(guild_id: int, user_id: int, category_name: str) -> dict | None:
    """Vérifie si un joueur a déjà un ticket ouvert dans cette catégorie."""
    name_key = category_name.strip().lower()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND user_id = ? AND category_name = ?",
            (guild_id, user_id, name_key),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_ticket_by_channel(channel_id: int) -> dict | None:
    """Retourne les infos d'un ticket à partir de l'ID de son salon."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def claim_ticket(channel_id: int, staff_user_id: int) -> dict:
    """Prend en charge un ticket de façon atomique."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        )).fetchone()
        if row is None:
            await db.rollback()
            return {"status": "not_found"}
        ticket = dict(row)
        if ticket.get("claimed_by") == staff_user_id:
            await db.rollback()
            return {"status": "already_yours", "ticket": ticket}
        if ticket.get("claimed_by") is not None:
            await db.rollback()
            return {"status": "already_claimed", "ticket": ticket}
        claimed_at = _now_iso()
        await db.execute(
            "UPDATE tickets SET claimed_by = ?, claimed_at = ? WHERE channel_id = ?",
            (staff_user_id, claimed_at, channel_id),
        )
        await db.commit()
        ticket["claimed_by"] = staff_user_id
        ticket["claimed_at"] = claimed_at
        return {"status": "ok", "ticket": ticket}


async def unclaim_ticket(channel_id: int) -> dict:
    """Libère la prise en charge d'un ticket de façon atomique."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        )).fetchone()
        if row is None:
            await db.rollback()
            return {"status": "not_found"}
        ticket = dict(row)
        if ticket.get("claimed_by") is None:
            await db.rollback()
            return {"status": "not_claimed", "ticket": ticket}
        previous_claimant = ticket["claimed_by"]
        await db.execute(
            "UPDATE tickets SET claimed_by = NULL, claimed_at = NULL WHERE channel_id = ?",
            (channel_id,),
        )
        await db.commit()
        ticket["claimed_by"] = None
        ticket["claimed_at"] = None
        return {"status": "ok", "ticket": ticket, "previous_claimant": previous_claimant}


async def close_ticket(channel_id: int):
    """Retire un ticket de la base (à appeler quand son salon est supprimé)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("DELETE FROM tickets WHERE channel_id = ?", (channel_id,))
        await db.commit()


async def set_ticket_log_channel(guild_id: int, channel_id: int):
    """Définit le salon où seront envoyées les transcriptions de tickets."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO ticket_settings (guild_id, log_channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id",
            (guild_id, channel_id),
        )
        await db.commit()


async def get_ticket_log_channel(guild_id: int) -> int | None:
    """Retourne l'ID du salon de logs de tickets configuré, ou None."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT log_channel_id FROM ticket_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


# --- Avertissements (/warn) ---

async def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    """Ajoute un avertissement et retourne son ID."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, _now_iso()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_warnings(guild_id: int, user_id: int) -> list[dict]:
    """Retourne tous les avertissements d'un membre, du plus récent au plus ancien."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_warning_count(guild_id: int, user_id: int) -> int:
    """Retourne le nombre total d'avertissements actifs d'un membre."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        (count,) = await cursor.fetchone()
        return count


async def remove_warning(warning_id: int, guild_id: int) -> bool:
    """Supprime un avertissement précis. Retourne True s'il existait."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
            (warning_id, guild_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def clear_warnings(guild_id: int, user_id: int) -> int:
    """Supprime tous les avertissements d'un membre. Retourne le nombre supprimé."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        return cursor.rowcount


# --- Système de logs (configurable par catégorie) ---

async def set_log_channel(guild_id: int, category: str, channel_id: int):
    """Active (ou met à jour) le salon de logs pour une catégorie donnée."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO log_settings (guild_id, category, channel_id, enabled) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(guild_id, category) DO UPDATE SET channel_id = excluded.channel_id, enabled = 1",
            (guild_id, category, channel_id),
        )
        await db.commit()


async def disable_log_category(guild_id: int, category: str):
    """Désactive une catégorie de logs (conserve le salon configuré pour une réactivation rapide)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE log_settings SET enabled = 0 WHERE guild_id = ? AND category = ?",
            (guild_id, category),
        )
        await db.commit()


async def get_log_channel(guild_id: int, category: str) -> int | None:
    """Retourne l'ID du salon de logs actif pour cette catégorie, ou None si désactivé/non configuré."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT channel_id FROM log_settings WHERE guild_id = ? AND category = ? AND enabled = 1",
            (guild_id, category),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_all_log_settings(guild_id: int) -> list[dict]:
    """Retourne la configuration de toutes les catégories de logs pour ce serveur."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM log_settings WHERE guild_id = ?",
            (guild_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# --- Tags de serveur Discord ---

async def add_server_tag_rule(
    guild_id: int,
    tag: str,
    tag_key: str,
    source_guild_id: int,
    role_id: int,
    created_by: int,
) -> int:
    """Ajoute une règle tag -> rôle et retourne son identifiant."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO server_tag_rules "
            "(guild_id, tag, tag_key, source_guild_id, role_id, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, tag_key, source_guild_id, role_id) DO UPDATE SET "
            "tag = excluded.tag, created_by = excluded.created_by, created_at = excluded.created_at",
            (guild_id, tag, tag_key, source_guild_id, role_id, created_by, _now_iso()),
        )
        row = await (await db.execute(
            "SELECT id FROM server_tag_rules WHERE guild_id = ? AND tag_key = ? "
            "AND source_guild_id = ? AND role_id = ?",
            (guild_id, tag_key, source_guild_id, role_id),
        )).fetchone()
        await db.commit()
        return int(row[0])


async def get_server_tag_rules(guild_id: int) -> list[dict]:
    """Retourne toutes les règles de tags d'un serveur."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM server_tag_rules WHERE guild_id = ? ORDER BY tag_key, id",
            (guild_id,),
        )).fetchall()
        return [dict(row) for row in rows]


async def get_server_tag_rule(guild_id: int, rule_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM server_tag_rules WHERE guild_id = ? AND id = ?",
            (guild_id, rule_id),
        )).fetchone()
        return dict(row) if row else None


async def delete_server_tag_rule(guild_id: int, rule_id: int) -> bool:
    """Supprime une règle et ses attributions enregistrées."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM server_tag_assignments WHERE guild_id = ? AND rule_id = ?",
            (guild_id, rule_id),
        )
        cursor = await db.execute(
            "DELETE FROM server_tag_rules WHERE guild_id = ? AND id = ?",
            (guild_id, rule_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def save_server_tag_assignment(
    rule_id: int,
    guild_id: int,
    user_id: int,
    role_id: int,
):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO server_tag_assignments "
            "(rule_id, guild_id, user_id, role_id, assigned_at) VALUES (?, ?, ?, ?, ?)",
            (rule_id, guild_id, user_id, role_id, _now_iso()),
        )
        await db.commit()


async def has_server_tag_assignment(rule_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        row = await (await db.execute(
            "SELECT 1 FROM server_tag_assignments WHERE rule_id = ? AND user_id = ?",
            (rule_id, user_id),
        )).fetchone()
        return row is not None


async def delete_server_tag_assignment(rule_id: int, user_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM server_tag_assignments WHERE rule_id = ? AND user_id = ?",
            (rule_id, user_id),
        )
        await db.commit()


async def get_server_tag_rule_assignments(guild_id: int, rule_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM server_tag_assignments WHERE guild_id = ? AND rule_id = ?",
            (guild_id, rule_id),
        )).fetchall()
        return [dict(row) for row in rows]


# --- Verrouillage de salons (/lock, /unlock) ---

async def save_lock_state(guild_id: int, channel_id: int, previous_value: bool | None, locked_by: int):
    """
    Enregistre l'état AVANT verrouillage (True/False/None) pour pouvoir le
    restaurer exactement avec /unlock, plutôt que de faire un reset brutal.
    """
    stored = None if previous_value is None else int(previous_value)
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO locked_channels (channel_id, guild_id, previous_send_messages, locked_by, locked_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(channel_id) DO UPDATE SET "
            "previous_send_messages = excluded.previous_send_messages, "
            "locked_by = excluded.locked_by, locked_at = excluded.locked_at",
            (channel_id, guild_id, stored, locked_by, _now_iso()),
        )
        await db.commit()


async def get_lock_state(channel_id: int) -> dict | None:
    """Retourne l'état de verrouillage d'un salon, ou None s'il n'est pas verrouillé."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM locked_channels WHERE channel_id = ?", (channel_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = dict(row)
        raw = data["previous_send_messages"]
        data["previous_send_messages"] = None if raw is None else bool(raw)
        return data


async def remove_lock_state(channel_id: int):
    """Retire l'enregistrement de verrouillage d'un salon (à appeler après /unlock)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("DELETE FROM locked_channels WHERE channel_id = ?", (channel_id,))
        await db.commit()


# --- Profils Blox Fruits (bounty + build, indépendant de l'économie du bot) ---

async def set_bloxfruits_profile(
    user_id: int,
    guild_id: int,
    bounty: str,
    fruit: str | None = None,
    sword: str | None = None,
    gun: str | None = None,
    fighting_style: str | None = None,
):
    """Crée ou met à jour le profil Blox Fruits (bounty + équipement détaillé) d'un membre."""
    # "build" est conservé (colonne historique) comme résumé lisible, pour compat descendante
    build_summary = " / ".join(filter(None, [fruit, sword, gun, fighting_style])) or "Non précisé"

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO blox_fruits_profiles "
            "(user_id, guild_id, bounty, build, fruit, sword, gun, fighting_style, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET "
            "bounty = excluded.bounty, build = excluded.build, fruit = excluded.fruit, "
            "sword = excluded.sword, gun = excluded.gun, fighting_style = excluded.fighting_style, "
            "updated_at = excluded.updated_at",
            (user_id, guild_id, bounty, build_summary, fruit, sword, gun, fighting_style, _now_iso()),
        )
        await db.commit()


async def get_bloxfruits_profile(user_id: int, guild_id: int) -> dict | None:
    """Retourne le profil Blox Fruits d'un membre, ou None s'il n'en a pas renseigné."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM blox_fruits_profiles WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_bloxfruits_profiles(guild_id: int) -> list[dict]:
    """Retourne tous les profils Blox Fruits renseignés sur ce serveur."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM blox_fruits_profiles WHERE guild_id = ?",
            (guild_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# --- Mode "tracking" des tickets (statut public suivi en direct) ---

async def set_tracking_channel(guild_id: int, channel_id: int):
    """Définit le salon public où seront postés les messages de suivi de tickets."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO ticket_settings (guild_id, log_channel_id, tracking_channel_id) VALUES (?, NULL, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET tracking_channel_id = excluded.tracking_channel_id",
            (guild_id, channel_id),
        )
        await db.commit()


async def get_tracking_channel(guild_id: int) -> int | None:
    """Retourne l'ID du salon de suivi public configuré, ou None."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT tracking_channel_id FROM ticket_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def start_tracking(
    channel_id: int,
    guild_id: int,
    status_channel_id: int,
    status_message_id: int,
    tracked_by: int,
    status: str = "attente",
):
    """Enregistre le suivi public d'un ticket (et le message de statut associé)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO tracked_tickets "
            "(channel_id, guild_id, status_channel_id, status_message_id, tracked_by, tracked_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(channel_id) DO UPDATE SET "
            "status_channel_id = excluded.status_channel_id, "
            "status_message_id = excluded.status_message_id, "
            "tracked_by = excluded.tracked_by, tracked_at = excluded.tracked_at, status = excluded.status",
            (channel_id, guild_id, status_channel_id, status_message_id, tracked_by, _now_iso(), status),
        )
        await db.commit()


async def update_tracked_ticket_status(channel_id: int, status: str):
    """Mémorise l'état courant pour pouvoir rafraîchir le suivi lors d'un claim."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE tracked_tickets SET status = ? WHERE channel_id = ?",
            (status, channel_id),
        )
        await db.commit()


async def get_tracked_ticket(channel_id: int) -> dict | None:
    """Retourne les infos de suivi d'un ticket, ou None s'il n'est pas suivi."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tracked_tickets WHERE channel_id = ?", (channel_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def stop_tracking(channel_id: int):
    """Arrête le suivi public d'un ticket."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("DELETE FROM tracked_tickets WHERE channel_id = ?", (channel_id,))
        await db.commit()


# --- Giveaways ---

async def create_giveaway(data: dict):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO giveaways (message_id, guild_id, channel_id, prize, winner_count, ends_at, "
            "required_role_id, bypass_role_id, min_account_age_seconds, min_membership_seconds, host_id, "
            "prize_item_id, prize_points) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["message_id"], data["guild_id"], data["channel_id"], data["prize"],
             data["winner_count"], data["ends_at"], data.get("required_role_id"),
             data.get("bypass_role_id"), data["min_account_age_seconds"],
             data["min_membership_seconds"], data["host_id"], data.get("prize_item_id"),
             data.get("prize_points", 0)),
        )
        await db.commit()


async def get_giveaway(message_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM giveaways WHERE message_id = ?", (message_id,)
        )).fetchone()
        return dict(row) if row else None


async def get_active_giveaways() -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM giveaways WHERE ended = 0")).fetchall()
        return [dict(row) for row in rows]


async def enter_giveaway(message_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO giveaway_entries (message_id, user_id, entered_at) VALUES (?, ?, ?)",
            (message_id, user_id, _now_iso()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_giveaway_entries(message_id: int) -> list[int]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        rows = await (await db.execute(
            "SELECT user_id FROM giveaway_entries WHERE message_id = ?", (message_id,)
        )).fetchall()
        return [row[0] for row in rows]


async def end_giveaway(message_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))
        await db.commit()


async def upsert_giveaway_prize_item(
    guild_id: int, name: str, points: int, emoji: str, created_by: int
) -> dict:
    """Crée ou met à jour un lot sélectionnable pour les giveaways d'un serveur."""
    now = _now_iso()
    name_key = name.casefold()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO giveaway_prize_items "
            "(guild_id, name, name_key, points, emoji, active, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?) "
            "ON CONFLICT(guild_id, name_key) DO UPDATE SET "
            "name=excluded.name, points=excluded.points, emoji=excluded.emoji, active=1, "
            "created_by=excluded.created_by, updated_at=excluded.updated_at",
            (guild_id, name, name_key, points, emoji, created_by, now, now),
        )
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM giveaway_prize_items WHERE guild_id = ? AND name_key = ?",
            (guild_id, name_key),
        )).fetchone()
        await db.commit()
        return dict(row)


async def get_giveaway_prize_items(guild_id: int, include_inactive: bool = False) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM giveaway_prize_items WHERE guild_id = ?"
        if not include_inactive:
            query += " AND active = 1"
        query += " ORDER BY name COLLATE NOCASE"
        rows = await (await db.execute(query, (guild_id,))).fetchall()
        return [dict(row) for row in rows]


async def get_giveaway_prize_item(guild_id: int, item_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM giveaway_prize_items WHERE guild_id = ? AND id = ? AND active = 1",
            (guild_id, item_id),
        )).fetchone()
        return dict(row) if row else None


async def search_giveaway_prize_items(guild_id: int, query: str, limit: int = 25) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM giveaway_prize_items WHERE guild_id = ? AND active = 1 "
            "AND name_key LIKE ? ORDER BY name COLLATE NOCASE LIMIT ?",
            (guild_id, f"%{query.casefold()}%", limit),
        )).fetchall()
        return [dict(row) for row in rows]


async def deactivate_giveaway_prize_item(guild_id: int, item_id: int) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE giveaway_prize_items SET active = 0, updated_at = ? WHERE guild_id = ? AND id = ?",
            (_now_iso(), guild_id, item_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def set_giveaway_points_name(guild_id: int, points_name: str):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO giveaway_point_settings (guild_id, points_name) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET points_name = excluded.points_name",
            (guild_id, points_name),
        )
        await db.commit()


async def get_giveaway_points_name(guild_id: int) -> str:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        row = await (await db.execute(
            "SELECT points_name FROM giveaway_point_settings WHERE guild_id = ?", (guild_id,)
        )).fetchone()
        return row[0] if row else "Points"


async def add_giveaway_point_role(
    guild_id: int, role_id: int, points_required: int, created_by: int
):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO giveaway_point_roles (guild_id, role_id, points_required, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(guild_id, role_id) DO UPDATE SET "
            "points_required=excluded.points_required, created_by=excluded.created_by, "
            "created_at=excluded.created_at",
            (guild_id, role_id, points_required, created_by, _now_iso()),
        )
        await db.commit()


async def get_giveaway_point_roles(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM giveaway_point_roles WHERE guild_id = ? "
            "ORDER BY points_required ASC, role_id ASC",
            (guild_id,),
        )).fetchall()
        return [dict(row) for row in rows]


async def remove_giveaway_point_role(guild_id: int, role_id: int) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM giveaway_point_roles WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def award_giveaway_points(
    message_id: int, guild_id: int, user_id: int, points: int
) -> int | None:
    """Attribue les points d'un giveaway une seule fois et retourne le nouveau solde."""
    if points <= 0:
        return 0
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "INSERT OR IGNORE INTO giveaway_point_awards "
            "(message_id, user_id, guild_id, points, awarded_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, user_id, guild_id, points, _now_iso()),
        )
        if cursor.rowcount == 0:
            await db.commit()
            return None
        await db.execute(
            "INSERT INTO giveaway_member_points (guild_id, user_id, points, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "points = points + excluded.points, updated_at = excluded.updated_at",
            (guild_id, user_id, points, _now_iso()),
        )
        row = await (await db.execute(
            "SELECT points FROM giveaway_member_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )).fetchone()
        await db.commit()
        return int(row[0])


async def add_giveaway_member_points(guild_id: int, user_id: int, points: int) -> int:
    """Ajoute manuellement des points et retourne le nouveau solde."""
    if points <= 0:
        raise ValueError("Le nombre de points doit être positif.")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO giveaway_member_points (guild_id, user_id, points, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "points = points + excluded.points, updated_at = excluded.updated_at",
            (guild_id, user_id, points, _now_iso()),
        )
        row = await (await db.execute(
            "SELECT points FROM giveaway_member_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )).fetchone()
        await db.commit()
        return int(row[0])


async def create_giveaway_proposal(data: dict) -> int:
    """Enregistre une proposition provenant d'un ticket et retourne son identifiant."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO giveaway_proposals "
            "(guild_id, ticket_channel_id, proposer_id, prize_item_id, prize_name, prize_points, status, created_at, "
            "duration_seconds, target_channel_id, winner_count, required_role_id, bypass_role_id, "
            "min_account_age_seconds, min_membership_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["guild_id"], data["ticket_channel_id"], data["proposer_id"],
             data.get("prize_item_id"), data["prize_name"], data["prize_points"], _now_iso(),
             data["duration_seconds"], data["target_channel_id"], data["winner_count"],
             data.get("required_role_id"), data.get("bypass_role_id"),
             data["min_account_age_seconds"], data["min_membership_seconds"]),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def delete_giveaway_proposal(proposal_id: int):
    """Supprime une proposition non publiée lorsqu'aucun message de log n'a pu être créé."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM giveaway_proposals WHERE id = ? AND status = 'pending' AND log_message_id IS NULL",
            (proposal_id,),
        )
        await db.commit()


async def get_giveaway_proposal(proposal_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM giveaway_proposals WHERE id = ?", (proposal_id,)
        )).fetchone()
        return dict(row) if row else None


async def get_pending_giveaway_proposal_for_ticket(ticket_channel_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM giveaway_proposals WHERE ticket_channel_id = ? AND status = 'pending' "
            "ORDER BY id DESC LIMIT 1",
            (ticket_channel_id,),
        )).fetchone()
        return dict(row) if row else None


async def get_pending_giveaway_proposals() -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM giveaway_proposals WHERE status = 'pending' AND log_message_id IS NOT NULL"
        )).fetchall()
        return [dict(row) for row in rows]


async def set_giveaway_proposal_log(proposal_id: int, channel_id: int, message_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE giveaway_proposals SET log_channel_id = ?, log_message_id = ? WHERE id = ?",
            (channel_id, message_id, proposal_id),
        )
        await db.commit()


async def set_giveaway_proposal_status_message(proposal_id: int, message_id: int):
    """Mémorise le message public de statut affiché dans le ticket."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE giveaway_proposals SET status_message_id = ? WHERE id = ?",
            (message_id, proposal_id),
        )
        await db.commit()


async def review_giveaway_proposal(proposal_id: int, guild_id: int, status: str, reviewer_id: int) -> bool:
    """Verrouille la décision du staff ; une proposition ne peut être traitée qu'une fois."""
    if status not in {"approved", "denied"}:
        raise ValueError("Statut de proposition invalide.")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE giveaway_proposals SET status = ?, reviewed_by = ?, reviewed_at = ? "
            "WHERE id = ? AND guild_id = ? AND status = 'pending'",
            (status, reviewer_id, _now_iso(), proposal_id, guild_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def approve_published_giveaway_proposal(proposal_id: int, guild_id: int, reviewer_id: int,
                                             message_id: int, giveaway: dict) -> bool:
    """Enregistre giveaway et approbation ensemble dans une transaction SQLite."""
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        row = await (await conn.execute(
            "SELECT status FROM giveaway_proposals WHERE id = ? AND guild_id = ?",
            (proposal_id, guild_id),
        )).fetchone()
        if not row or row[0] != "pending":
            await conn.rollback()
            return False
        await conn.execute(
            "INSERT INTO giveaways (message_id, guild_id, channel_id, prize, winner_count, ends_at, "
            "required_role_id, bypass_role_id, min_account_age_seconds, min_membership_seconds, "
            "host_id, prize_item_id, prize_points) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, guild_id, giveaway["channel_id"], giveaway["prize"],
             giveaway["winner_count"], giveaway["ends_at"], giveaway.get("required_role_id"),
             giveaway.get("bypass_role_id"), giveaway["min_account_age_seconds"],
             giveaway["min_membership_seconds"], giveaway["host_id"],
             giveaway.get("prize_item_id"), giveaway.get("prize_points", 0)),
        )
        await conn.execute(
            "UPDATE giveaway_proposals SET status = 'approved', reviewed_by = ?, reviewed_at = ?, "
            "published_message_id = ? WHERE id = ? AND guild_id = ?",
            (reviewer_id, _now_iso(), message_id, proposal_id, guild_id),
        )
        await conn.commit()
        return True


async def get_giveaway_member_points(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        row = await (await db.execute(
            "SELECT points FROM giveaway_member_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )).fetchone()
        return int(row[0]) if row else 0


async def get_giveaway_member_point_balances(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM giveaway_member_points WHERE guild_id = ? AND points > 0 ORDER BY points DESC",
            (guild_id,),
        )).fetchall()
        return [dict(row) for row in rows]


# --- Anti-raid ---

async def set_antiraid_settings(guild_id: int, enabled: bool, threshold: int, window: int,
                                min_age: int, log_channel_id: int | None, bypass_role_id: int | None):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO antiraid_settings (guild_id, enabled, join_threshold, window_seconds, "
            "min_account_age_seconds, log_channel_id, bypass_role_id) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET enabled=excluded.enabled, "
            "join_threshold=excluded.join_threshold, window_seconds=excluded.window_seconds, "
            "min_account_age_seconds=excluded.min_account_age_seconds, "
            "log_channel_id=excluded.log_channel_id, bypass_role_id=excluded.bypass_role_id",
            (guild_id, int(enabled), threshold, window, min_age, log_channel_id, bypass_role_id),
        )
        await db.commit()


async def get_antiraid_settings(guild_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM antiraid_settings WHERE guild_id = ?", (guild_id,)
        )).fetchone()
        return dict(row) if row else None


async def copy_warnings(source_guild_id: int, target_guild_id: int) -> int:
    """Copie les avertissements absents vers un autre serveur sans dupliquer les imports."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        rows = await (await db.execute(
            "SELECT user_id, moderator_id, reason, created_at FROM warnings WHERE guild_id = ?",
            (source_guild_id,),
        )).fetchall()
        copied = 0
        for user_id, moderator_id, reason, created_at in rows:
            exists = await (await db.execute(
                "SELECT 1 FROM warnings WHERE guild_id = ? AND user_id = ? AND moderator_id = ? "
                "AND reason = ? AND created_at = ?",
                (target_guild_id, user_id, moderator_id, reason, created_at),
            )).fetchone()
            if not exists:
                await db.execute(
                    "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (target_guild_id, user_id, moderator_id, reason, created_at),
                )
                copied += 1
        await db.commit()
        return copied


# --- Registre partagé des sanctions ---

async def add_sanction_record(guild_id: int, user_id: int, username: str, display_name: str,
                              sanction_type: str, moderator_id: int | None,
                              moderator_name: str | None, reason: str,
                              duration_seconds: int | None = None) -> int:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO sanction_records (guild_id, user_id, username, display_name, sanction_type, "
            "moderator_id, moderator_name, reason, duration_seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, username, display_name, sanction_type, moderator_id,
             moderator_name, reason, duration_seconds, _now_iso()),
        )
        await db.commit()
        return cursor.lastrowid


async def search_sanction_records(query: str, guild_id: int | None = None,
                                  limit: int = 25) -> list[dict]:
    cleaned = query.strip()
    if cleaned.startswith("<@") and cleaned.endswith(">"):
        cleaned = cleaned[2:-1].lstrip("!")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if cleaned.isdigit() and guild_id is not None:
            cursor = await db.execute(
                "SELECT * FROM sanction_records WHERE guild_id = ? AND user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (guild_id, int(cleaned), limit),
            )
        elif cleaned.isdigit():
            cursor = await db.execute(
                "SELECT * FROM sanction_records WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (int(cleaned), limit),
            )
        elif guild_id is not None:
            pattern = f"%{cleaned.lower()}%"
            cursor = await db.execute(
                "SELECT * FROM sanction_records WHERE guild_id = ? AND "
                "(lower(username) LIKE ? OR lower(display_name) LIKE ?) "
                "ORDER BY id DESC LIMIT ?",
                (guild_id, pattern, pattern, limit),
            )
        else:
            pattern = f"%{cleaned.lower()}%"
            cursor = await db.execute(
                "SELECT * FROM sanction_records WHERE lower(username) LIKE ? OR lower(display_name) LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (pattern, pattern, limit),
            )
        return [dict(row) for row in await cursor.fetchall()]


async def set_sanction_log(source_guild_id: int, destination_guild_id: int, destination_channel_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO sanction_log_settings "
            "(source_guild_id, destination_guild_id, destination_channel_id) VALUES (?, ?, ?) "
            "ON CONFLICT(source_guild_id) DO UPDATE SET "
            "destination_guild_id=excluded.destination_guild_id, "
            "destination_channel_id=excluded.destination_channel_id",
            (source_guild_id, destination_guild_id, destination_channel_id),
        )
        await db.commit()


async def get_sanction_log(source_guild_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM sanction_log_settings WHERE source_guild_id = ?", (source_guild_id,)
        )).fetchone()
        return dict(row) if row else None


async def disable_sanction_log(source_guild_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("DELETE FROM sanction_log_settings WHERE source_guild_id = ?", (source_guild_id,))
        await db.commit()


async def get_all_warnings_for_guild(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM warnings WHERE guild_id = ? ORDER BY id", (guild_id,)
        )).fetchall()
        return [dict(row) for row in rows]


async def sanction_record_exists(guild_id: int, user_id: int, sanction_type: str, reason: str) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        row = await (await db.execute(
            "SELECT 1 FROM sanction_records WHERE guild_id = ? AND user_id = ? "
            "AND sanction_type = ? AND reason = ? LIMIT 1",
            (guild_id, user_id, sanction_type, reason),
        )).fetchone()
        return row is not None


# --- Liaison Roblox OAuth ---

async def create_roblox_oauth_state(state: str, discord_user_id: int, guild_id: int,
                                    code_verifier: str, expires_at: str):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("DELETE FROM roblox_oauth_states WHERE discord_user_id = ?", (discord_user_id,))
        await db.execute(
            "INSERT INTO roblox_oauth_states (state, discord_user_id, guild_id, code_verifier, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (state, discord_user_id, guild_id, code_verifier, expires_at),
        )
        await db.commit()


async def consume_roblox_oauth_state(state: str) -> dict | None:
    """Récupère et supprime un état OAuth en une transaction pour empêcher sa réutilisation."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute(
            "SELECT * FROM roblox_oauth_states WHERE state = ?", (state,)
        )).fetchone()
        await db.execute("DELETE FROM roblox_oauth_states WHERE state = ?", (state,))
        await db.commit()
        return dict(row) if row else None


async def save_roblox_link(discord_user_id: int, guild_id: int, profile: dict) -> tuple[bool, str | None]:
    """Enregistre une liaison. Refuse qu'un compte Roblox appartienne à deux Discord."""
    roblox_id = int(profile["sub"])
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        owner = await (await db.execute(
            "SELECT discord_user_id FROM roblox_links WHERE roblox_user_id = ?", (roblox_id,)
        )).fetchone()
        if owner and owner[0] != discord_user_id:
            return False, "Ce compte Roblox est déjà lié à un autre compte Discord."
        await db.execute(
            "INSERT INTO roblox_links (discord_user_id, roblox_user_id, roblox_username, "
            "roblox_display_name, profile_url, picture_url, roblox_created_at, linked_at, last_guild_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(discord_user_id) DO UPDATE SET roblox_user_id=excluded.roblox_user_id, "
            "roblox_username=excluded.roblox_username, roblox_display_name=excluded.roblox_display_name, "
            "profile_url=excluded.profile_url, picture_url=excluded.picture_url, "
            "roblox_created_at=excluded.roblox_created_at, linked_at=excluded.linked_at, "
            "last_guild_id=excluded.last_guild_id",
            (discord_user_id, roblox_id, profile.get("preferred_username") or profile.get("nickname") or str(roblox_id),
             profile.get("name") or profile.get("nickname") or "Inconnu", profile.get("profile"),
             profile.get("picture"), profile.get("created_at"), _now_iso(), guild_id),
        )
        await db.commit()
        return True, None


async def get_roblox_link(discord_user_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM roblox_links WHERE discord_user_id = ?", (discord_user_id,)
        )).fetchone()
        return dict(row) if row else None


async def delete_roblox_link(discord_user_id: int) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM roblox_links WHERE discord_user_id = ?", (discord_user_id,))
        await db.commit()
        return cursor.rowcount > 0


# --- Rôles d'arrivée ---

async def add_join_role(guild_id: int, role_id: int, target: str, created_by: int):
    """Ajoute (ou met à jour) un rôle donné automatiquement à l'arrivée."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO join_roles (guild_id, role_id, target, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, role_id) DO UPDATE SET "
            "target = excluded.target, created_by = excluded.created_by, created_at = excluded.created_at",
            (guild_id, role_id, target, created_by, _now_iso()),
        )
        await db.commit()


async def remove_join_role(guild_id: int, role_id: int) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM join_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_join_roles(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM join_roles WHERE guild_id = ? ORDER BY created_at, role_id", (guild_id,)
        )).fetchall()
        return [dict(row) for row in rows]


async def get_join_role_settings(guild_id: int) -> dict:
    """Réglages des rôles d'arrivée (par défaut : attendre la validation du règlement)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        row = await (await db.execute(
            "SELECT wait_screening FROM join_role_settings WHERE guild_id = ?", (guild_id,)
        )).fetchone()
        return {"wait_screening": bool(row[0]) if row else True}


async def set_join_role_wait_screening(guild_id: int, wait: bool):
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO join_role_settings (guild_id, wait_screening) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET wait_screening = excluded.wait_screening",
            (guild_id, int(wait)),
        )
        await db.commit()


# --- Messages Discord éditables depuis le site ---

async def get_message_editor_roles(guild_id: int) -> list[int]:
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        rows = await (await conn.execute(
            "SELECT role_id FROM panel_message_editor_roles WHERE guild_id = ? ORDER BY role_id",
            (guild_id,),
        )).fetchall()
        return [row[0] for row in rows]


async def set_message_editor_roles(guild_id: int, role_ids: list[int]):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        await conn.execute("DELETE FROM panel_message_editor_roles WHERE guild_id = ?", (guild_id,))
        await conn.executemany(
            "INSERT INTO panel_message_editor_roles (guild_id, role_id) VALUES (?, ?)",
            [(guild_id, role_id) for role_id in sorted(set(role_ids))],
        )
        await conn.commit()


async def list_panel_messages(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT * FROM panel_messages WHERE guild_id = ? ORDER BY created_at DESC LIMIT 200",
            (guild_id,),
        )).fetchall()
        return [dict(row) for row in rows]


async def get_panel_message(guild_id: int, message_id: int) -> dict | None:
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM panel_messages WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )).fetchone()
        return dict(row) if row else None


async def save_panel_message(guild_id: int, channel_id: int, message_id: int,
                             values: dict, user_id: int):
    now = _now_iso()
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            "INSERT INTO panel_messages (guild_id, channel_id, message_id, message_type, content, "
            "embed_title, embed_description, embed_color, embed_footer, embed_image, "
            "created_by, updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, message_id) DO UPDATE SET "
            "message_type=excluded.message_type, content=excluded.content, "
            "embed_title=excluded.embed_title, embed_description=excluded.embed_description, "
            "embed_color=excluded.embed_color, embed_footer=excluded.embed_footer, "
            "embed_image=excluded.embed_image, updated_by=excluded.updated_by, "
            "updated_at=excluded.updated_at",
            (guild_id, channel_id, message_id, values['message_type'], values['content'],
             values['embed_title'], values['embed_description'], values['embed_color'],
             values['embed_footer'], values['embed_image'], user_id, user_id, now, now),
        )
        await conn.commit()


async def remove_panel_message(guild_id: int, message_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            "DELETE FROM panel_messages WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        await conn.commit()


# --- Reaction roles ---
async def create_reaction_role_panel(guild_id: int, channel_id: int, message_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            "INSERT INTO reaction_role_panels(guild_id,channel_id,message_id) VALUES(?,?,?)",
            (guild_id, channel_id, message_id),
        )
        await conn.commit()


async def get_reaction_role_panel(guild_id: int, message_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM reaction_role_panels WHERE guild_id=? AND message_id=?",
            (guild_id, message_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def list_reaction_role_panels(guild_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM reaction_role_panels WHERE guild_id=? ORDER BY message_id DESC",
            (guild_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def upsert_reaction_role_mapping(guild_id: int, message_id: int, emoji_key: str,
                                       emoji_display: str, role_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            "INSERT INTO reaction_role_mappings(guild_id,message_id,emoji_key,emoji_display,role_id) "
            "VALUES(?,?,?,?,?) ON CONFLICT(guild_id,message_id,emoji_key) DO UPDATE SET "
            "emoji_display=excluded.emoji_display,role_id=excluded.role_id",
            (guild_id, message_id, emoji_key, emoji_display, role_id),
        )
        await conn.commit()


async def get_reaction_role_mapping(guild_id: int, message_id: int, emoji_key: str):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT p.channel_id, m.role_id FROM reaction_role_mappings m "
            "JOIN reaction_role_panels p ON p.guild_id=m.guild_id AND p.message_id=m.message_id "
            "WHERE m.guild_id=? AND m.message_id=? AND m.emoji_key=?",
            (guild_id, message_id, emoji_key),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def list_reaction_role_mappings(guild_id: int, message_id: int):
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT emoji_key,emoji_display,role_id FROM reaction_role_mappings "
            "WHERE guild_id=? AND message_id=? ORDER BY emoji_key",
            (guild_id, message_id),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def delete_reaction_role_mapping(guild_id: int, message_id: int, emoji_key: str) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        cursor = await conn.execute(
            "DELETE FROM reaction_role_mappings WHERE guild_id=? AND message_id=? AND emoji_key=?",
            (guild_id, message_id, emoji_key),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def delete_reaction_role_panel(guild_id: int, message_id: int) -> bool:
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute("DELETE FROM reaction_role_mappings WHERE guild_id=? AND message_id=?",
                           (guild_id, message_id))
        cursor = await conn.execute("DELETE FROM reaction_role_panels WHERE guild_id=? AND message_id=?",
                                    (guild_id, message_id))
        await conn.commit()
        return cursor.rowcount > 0


# --- RYUKAI : profils de war et historique des résultats ---

_RYUKAI_STAT_COLUMNS = {
    "war": ("war_wins", "war_losses"),
    "pub_war": ("pub_war_wins", "pub_war_losses"),
    "duel": ("duel_wins", "duel_losses"),
}


async def get_ryukai_profile(user_id: int, guild_id: int) -> dict:
    """Retourne les métadonnées et statistiques RYUKAI d'un membre.

    Aucun profil explicite n'est requis : des valeurs par défaut permettent à
    ``/profile`` de fonctionner pour tous les membres dès le déploiement.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "INSERT OR IGNORE INTO ryukai_profiles "
            "(guild_id, user_id, updated_at) VALUES (?, ?, ?)",
            (guild_id, user_id, _now_iso()),
        )
        await conn.execute(
            "INSERT OR IGNORE INTO ryukai_stats (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        await conn.commit()
        row = await (await conn.execute(
            "SELECT p.team, p.rank_name, p.platform, p.region, "
            "s.war_wins, s.war_losses, s.pub_war_wins, s.pub_war_losses, "
            "s.duel_wins, s.duel_losses "
            "FROM ryukai_profiles p JOIN ryukai_stats s "
            "ON p.guild_id = s.guild_id AND p.user_id = s.user_id "
            "WHERE p.guild_id = ? AND p.user_id = ?",
            (guild_id, user_id),
        )).fetchone()
        return dict(row)


async def set_ryukai_profile(
    user_id: int,
    guild_id: int,
    team: str,
    rank_name: str,
    platform: str,
    region: str,
) -> None:
    """Crée ou met à jour les informations affichées sur la carte RYUKAI."""
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            "INSERT INTO ryukai_profiles "
            "(guild_id, user_id, team, rank_name, platform, region, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "team=excluded.team, rank_name=excluded.rank_name, "
            "platform=excluded.platform, region=excluded.region, "
            "updated_at=excluded.updated_at",
            (guild_id, user_id, team, rank_name, platform, region, _now_iso()),
        )
        await conn.execute(
            "INSERT OR IGNORE INTO ryukai_stats (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        await conn.commit()


async def record_ryukai_result(
    guild_id: int,
    match_type: str,
    winner_ids: list[int],
    loser_ids: list[int],
    recorded_by: int,
    note: str = "",
) -> int:
    """Enregistre un résultat et incrémente chaque participant atomiquement.

    Les identifiants du gagnant et du perdant doivent être disjoints. Le
    résultat renvoyé est l'identifiant historique utilisable pour l'audit.
    """
    if match_type not in _RYUKAI_STAT_COLUMNS:
        raise ValueError("Type de match RYUKAI invalide.")
    winners, losers = set(winner_ids), set(loser_ids)
    if not winners or not losers or winners & losers:
        raise ValueError("Les équipes gagnante et perdante doivent être non vides et distinctes.")

    win_column, loss_column = _RYUKAI_STAT_COLUMNS[match_type]
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("BEGIN IMMEDIATE")
        cursor = await conn.execute(
            "INSERT INTO ryukai_war_results "
            "(guild_id, match_type, recorded_by, recorded_at, note) VALUES (?, ?, ?, ?, ?)",
            (guild_id, match_type, recorded_by, _now_iso(), note),
        )
        result_id = cursor.lastrowid
        participants = [(result_id, user_id, "win") for user_id in sorted(winners)]
        participants += [(result_id, user_id, "loss") for user_id in sorted(losers)]
        await conn.executemany(
            "INSERT INTO ryukai_war_participants (result_id, user_id, outcome) VALUES (?, ?, ?)",
            participants,
        )
        for user_id in winners | losers:
            await conn.execute(
                "INSERT OR IGNORE INTO ryukai_stats (guild_id, user_id) VALUES (?, ?)",
                (guild_id, user_id),
            )
        await conn.executemany(
            f"UPDATE ryukai_stats SET {win_column} = {win_column} + 1 "
            "WHERE guild_id = ? AND user_id = ?",
            [(guild_id, user_id) for user_id in winners],
        )
        await conn.executemany(
            f"UPDATE ryukai_stats SET {loss_column} = {loss_column} + 1 "
            "WHERE guild_id = ? AND user_id = ?",
            [(guild_id, user_id) for user_id in losers],
        )
        await conn.commit()
        return result_id
