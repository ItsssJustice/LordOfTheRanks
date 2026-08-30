"""
sql_update.py

Provides Discord_Member_Update, a function that upserts the in-memory
`members` collection (built from discord.py Member objects) into the
`discord_members` MySQL table.

Expected `members` schema, keyed by member.id (dict) or as a plain list
of the same per-member dicts:
    members[member.id] = {
        "id": member.id,
        "name_user": member.name,
        "discriminator": member.discriminator,
        "name_global": member.global_name,
        "name_display": member.display_name,
        "name_nick": member.nick,
        "roles": member.roles,
        "perms": member.guild_permissions,
        "bot": member.bot,
        "member": member
    }

Expected MySQL table schema:
    "discord_members": {
        "discord_id": "BIGINT PRIMARY KEY",
        "name_user": "VARCHAR(255) NOT NULL",
        "name_global": "VARCHAR(255) NOT NULL",
        "name_display": "VARCHAR(255) NOT NULL",
        "name_nick": "VARCHAR(255) NOT NULL",
        "promotion_rank_id": "SMALLINT DEFAULT 0",
        "discriminator": "INT",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP"
    },

    "discord_roles": {
        "discord_role_id": "BIGINT PRIMARY KEY",
        "discord_role_name": "VARCHAR(255)",
        "discord_moderator_level": "SMALLINT DEFAULT 0"
    },

    "discord_promotion_ranks": {
        "promotion_rank_id": "SMALLINT PRIMARY KEY",
        "discord_role_id": "BIGINT NOT NULL",
        "points_required": "SMALLINT",
        "membership_time_required": "SMALLINT",
        "automatic_promotion": "BOOL DEFAULT FALSE",
        "promotion_rank_id_progression": "SMALLINT"
    }

`promotion_rank_id` is derived, not read from `members`: for each member,
their discord.py `roles` are matched against `discord_promotion_ranks.
discord_role_id`. If one or more of the member's roles has an associated
promotion rank, the HIGHEST matching promotion_rank_id is written; if
none match, 0 is written. `created_at` is never written by this
function -- it's populated by the column default on insert and left
alone on update.

Only the columns that exist in the table are written; "perms", "bot",
and "member" are ignored since the table has no matching columns.

Usage:
    rowcount = sql_update.Discord_Member_Update(SQL_Connection, Guild_Member_List)
"""

from mysql.connector import Error as MySQLError

QUERY = """
    INSERT INTO discord_members
        (discord_id, name_user, name_global, name_display, name_nick,
         promotion_rank_id, discriminator)
    VALUES
        (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        name_user = VALUES(name_user),
        name_global = VALUES(name_global),
        name_display = VALUES(name_display),
        name_nick = VALUES(name_nick),
        promotion_rank_id = VALUES(promotion_rank_id),
        discriminator = VALUES(discriminator)
"""

ROLE_RANK_QUERY = """
    SELECT discord_role_id, promotion_rank_id
    FROM discord_promotion_ranks
"""


def _normalize(members, member_id):
    if member_id is not None:
        if not isinstance(members, dict):
            raise TypeError("member_id was given, but members is not a dict")
        if member_id not in members:
            raise KeyError(f"member_id {member_id} not found in members dict")
        return [members[member_id]]
    if isinstance(members, dict):
        return list(members.values())
    if isinstance(members, (list, tuple, set)):
        return list(members)
    raise TypeError(
        f"members must be a dict or a list of member dicts, got {type(members).__name__}"
    )


def _text(value):
    # Columns are NOT NULL VARCHAR; fall back to "" for None values.
    return "" if value is None else str(value)


def _discriminator(discriminator):
    # discord.py's discriminator is a string; "0" is the "no
    # discriminator" sentinel on the new username system -> NULL.
    if discriminator is None:
        return None
    try:
        value = int(discriminator)
    except (TypeError, ValueError):
        return None
    return None if value == 0 else value


def _load_role_rank_map(connection):
    """
    Build a {discord_role_id: promotion_rank_id} map from
    discord_promotion_ranks, for resolving a member's roles into a
    promotion rank.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(ROLE_RANK_QUERY)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {role_id: rank_id for role_id, rank_id in rows}


def _resolve_promotion_rank(data, role_rank_map):
    """
    Determine a member's promotion_rank_id from their discord.py roles.

    If more than one of the member's roles maps to a promotion rank,
    the highest promotion_rank_id is used. Members with no matching
    role get 0.
    """
    roles = data.get("roles") or []
    matched_ranks = [
        role_rank_map[role.id] for role in roles if role.id in role_rank_map
    ]
    return max(matched_ranks) if matched_ranks else 1


def Discord_Member_Update(connection, members, member_id=None):
    """
    Insert or update rows in `discord_members` based on `members`.

    For each member, `promotion_rank_id` is resolved by matching their
    discord.py roles against `discord_promotion_ranks.discord_role_id`
    (see module docstring for tie-breaking behavior).

    Args:
        connection: an open mysql.connector connection.
        members: a dict keyed by member.id, or a list of the same
            per-member dicts.
        member_id: optional. If provided (and members is a dict), only
            that single member is upserted instead of the whole collection.

    Returns:
        int: number of rows affected by the upsert (0 if there was
        nothing to do).
    """
    entries = _normalize(members, member_id)
    if not entries:
        return 0

    role_rank_map = _load_role_rank_map(connection)

    rows = [
        (
            data["id"],
            _text(data.get("name_user")),
            _text(data.get("name_global")),
            _text(data.get("name_display")),
            _text(data.get("name_nick")),
            _resolve_promotion_rank(data, role_rank_map),
            _discriminator(data.get("discriminator")),
        )
        for data in entries
    ]

    cursor = connection.cursor()
    try:
        cursor.executemany(QUERY, rows)
        connection.commit()
        rowcount = cursor.rowcount
    except MySQLError:
        connection.rollback()
        raise
    finally:
        cursor.close()

    return rowcount

#Determine if a discord user is a moderator and their respective level required
def Discord_Moderator_Level_Get(SQL_Cursor, discord_id):
    sql = "SELECT COALESCE(MAX(dr.discord_moderator_level), 0) AS moderator_level FROM discord_members AS m LEFT JOIN discord_promotion_roles AS pr ON pr.promotion_rank_id = m.promotion_rank_id LEFT JOIN discord_roles AS dr ON dr.discord_role_id = pr.discord_role_id WHERE m.discord_id = %s;"
    SQL_Cursor.execute(sql, (discord_id,))
    row = SQL_Cursor.fetchone()
    if row is None:
        return 0
    else:
        return row[0]

#Determine if a discord user is a moderator and if they have permissions to access a specific command with the respective level required
def Discord_Moderator_Command_Permitted(SQL_Cursor, discord_id, moderator_level_required):
    Assert_If_Moderator_Level_Allowed = True if Discord_Moderator_Level_Get(SQL_Cursor, discord_id) >= moderator_level_required else False
    return Assert_If_Moderator_Level_Allowed