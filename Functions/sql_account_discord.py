import datetime
from mysql.connector import Error as MySQLError
from Functions import sql_config

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

#normalise member id and member
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
    raise TypeError(f"members must be a dict or a list of member dicts, got {type(members).__name__}")

#Resolve null strings
def _text(value):
    # Columns are NOT NULL VARCHAR; fall back to "" for None values.
    return "" if value is None else str(value)

#resolve discord discriminator (0 is default)
def _discriminator(discriminator):
    if discriminator is None:
        return None
    try:
        value = int(discriminator)
    except (TypeError, ValueError):
        return None
    return None if value == 0 else value

#get discord promotion rank map, resolving their in game rank to a promotion index
def Promotion_Ranks_Get(SQL_Cursor):
    Query = "SELECT discord_role_id, promotion_rank_id FROM discord_promotion_ranks"
    return sql_config.Query_Dicts_Get(SQL_Cursor, Query)

# Resolve a discord user's promotion rank
def _resolve_promotion_rank(data, role_rank_map):
    roles = data.get("roles") or []
    matched_ranks = [role_rank_map[role.id] for role in roles if role.id in role_rank_map]
    return max(matched_ranks) if matched_ranks else 1

# Insert or Update discord members
def Members_List_Update(SQL_Connection, SQL_Cursor, members, member_id=None):
    entries = _normalize(members, member_id)
    if not entries:
        return 0
    role_rank_rows = Promotion_Ranks_Get(SQL_Cursor)
    #convert dict to map
    role_rank_map = {
        row["discord_role_id"]: row["promotion_rank_id"]
        for row in role_rank_rows
    }
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
    cursor = SQL_Connection.cursor()
    try:
        # Stamp when an existing member's rank changes, before the upsert below
        # overwrites the old value. Bound as a Python UTC instant rather than
        # NOW(), which follows the server's session timezone (see sql_poll.Polls_Search).
        # New members are left NULL: promotion_rules reads NULL as "no wait owed".
        Now = datetime.datetime.utcnow()
        Stamp_Rows = [(Now, Row[0], Row[5]) for Row in rows]
        cursor.executemany(
            "UPDATE discord_members SET promotion_rank_updated_at = %s WHERE discord_id = %s AND promotion_rank_id <> %s",
            Stamp_Rows)
        sql = """INSERT INTO discord_members (discord_id, name_user, name_global, name_display, name_nick, promotion_rank_id, discriminator) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE name_user = VALUES(name_user), name_global = VALUES(name_global), name_display = VALUES(name_display), name_nick = VALUES(name_nick), promotion_rank_id = VALUES(promotion_rank_id), discriminator = VALUES(discriminator)"""
        cursor.executemany(sql, rows)
        SQL_Connection.commit()
        rowcount = cursor.rowcount
    except MySQLError:
        SQL_Connection.rollback()
        raise
    finally:
        cursor.close()
    return rowcount

#Get all discord members
def Members_Get(SQL_Cursor) -> list[dict]:
    Query = "SELECT discord_id, name_user, name_global, name_display, name_nick, promotion_rank_id, discriminator, created_at FROM discord_members"
    return sql_config.Query_Dicts_Get(SQL_Cursor, Query)

#Display all discord members
def Members_Display(members: list[dict]):
    """Prints discord_members formatted in the console."""
    print(f"\n--- DISCORD MEMBERS ({len(members)} records) ---")
    header = f"{'Discord ID':<20} | {'User Name':<15} | {'Global Name':<15} | {'Display Name':<15} | {'Nick Name':<15}"
    print(header)
    print("-" * len(header))
    for m in members:
        print(
            f"{str(m['discord_id']):<20} | "
            f"{str(m['name_user']):<15} | "
            f"{str(m['name_global']):<15} | "
            f"{str(m['name_display']):<15} | "
            f"{str(m['name_nick']):<15}"
        )

# Insert or Update discord roles
def Roles_List_Update(SQL_Connection, SQL_Cursor, Guild_Role_List):
    if not Guild_Role_List:
        return 0
    rows = [
        (
            data["id"],
            _text(data.get("name")),
        )
        for data in Guild_Role_List
    ]
    cursor = SQL_Connection.cursor()
    try:
        sql = """INSERT INTO discord_roles (discord_role_id, discord_role_name) VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE discord_role_name = VALUES(discord_role_name)"""
        cursor.executemany(sql, rows)
        SQL_Connection.commit()
        rowcount = cursor.rowcount
    except MySQLError:
        SQL_Connection.rollback()
        raise
    finally:
        cursor.close()
    return rowcount