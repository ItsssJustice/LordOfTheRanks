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

#
def _load_role_rank_map(connection):
    """
    Build a {discord_role_id: promotion_rank_id} map from
    discord_promotion_ranks, for resolving a member's roles into a
    promotion rank.
    """
    cursor = connection.cursor()
    try:
        sql = "SELECT discord_role_id, promotion_rank_id FROM discord_promotion_ranks"
        cursor.execute(sql)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {role_id: rank_id for role_id, rank_id in rows}

# Resolve a discord user's promotion rank
def _resolve_promotion_rank(data, role_rank_map):
    roles = data.get("roles") or []
    matched_ranks = [role_rank_map[role.id] for role in roles if role.id in role_rank_map]
    return max(matched_ranks) if matched_ranks else 1

# Insert or Update discord members
def Members_List_Update(connection, members, member_id=None):
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
        sql = """INSERT INTO discord_members (discord_id, name_user, name_global, name_display, name_nick, promotion_rank_id, discriminator) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE name_user = VALUES(name_user), name_global = VALUES(name_global), name_display = VALUES(name_display), name_nick = VALUES(name_nick), promotion_rank_id = VALUES(promotion_rank_id), discriminator = VALUES(discriminator)"""
        cursor.executemany(sql, rows)
        connection.commit()
        rowcount = cursor.rowcount
    except MySQLError:
        connection.rollback()
        raise
    finally:
        cursor.close()

    return rowcount

# Insert or Update discord roles
def Roles_List_Update(connection, Guild_Role_List):
    if not Guild_Role_List:
        return 0
    rows = [
        (
            data["id"],
            _text(data.get("name")),
        )
        for data in Guild_Role_List
    ]
    cursor = connection.cursor()
    try:
        sql = """INSERT INTO discord_roles (discord_role_id, discord_role_name) VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE discord_role_name = VALUES(discord_role_name)"""
        cursor.executemany(sql, rows)
        connection.commit()
        rowcount = cursor.rowcount
    except MySQLError:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return rowcount