# Flatten the WOM group payload into a list of membership entries, optionally filtered to one player
def _normalize_wom(member_data, member_id=None):
    if not member_data:
        return []
    memberships = member_data.get("groupData", {}).get("memberships", [])
    if member_id is not None:
        memberships = [m for m in memberships if str(m.get("player_id")) == str(member_id)]
    return memberships

#Resolve null strings
def _text(value):
    # Columns are NOT NULL VARCHAR; fall back to "" for None values.
    return "" if value is None else str(value)

# Look up rank_id for a membership's WOM role, falling back to a default rank if unmapped
def _resolve_rank_id(entry, rank_map):
    role = entry.get("role")
    return rank_map.get(role, rank_map.get("_default", 0))

# Load the WOM role -> rank_id mapping.
# For each unseen role, case-insensitively match its name against discord_roles.discord_role_name;
# if a match exists, use discord_promotion_ranks.promotion_rank_id (via discord_role_id) as the
# osrs_role_id so the two stay aligned. Any role with no match gets the next free id.
def _load_rank_map(connection, roles=None):
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT osrs_role_name, osrs_role_id FROM osrs_roles")
        rank_map = {row[0]: row[1] for row in cursor.fetchall()}

        roles = [role for role in (roles or []) if role]
        if not roles:
            return rank_map

        missing = [role for role in roles if role not in rank_map]
        if not missing:
            return rank_map
        # Pull every discord role name -> promotion_rank_id pair for case-insensitive matching
        cursor.execute(
            """SELECT dr.discord_role_name, dpr.promotion_rank_id
               FROM discord_roles AS dr
               JOIN discord_promotion_ranks AS dpr
                   ON dpr.discord_role_id = dr.discord_role_id"""
        )
        # Ensure the name verification when comparing OSRS and discord roles are compliant (no spaces, all lowercase comparison)
        discord_rank_lookup = {
            name.lower().replace(" ", "_"): rank_id
            for name, rank_id in cursor.fetchall()
            if rank_id is not None
        }
        linked = []
        unlinked = []
        for role in missing:
            # Converted space to underscore to match dictionary keys
            rank_id = discord_rank_lookup.get(role.lower().replace(" ", "_"))
            if rank_id is not None:
                linked.append((rank_id, role))
            else:
                unlinked.append(role)
        if linked:
            cursor.executemany("INSERT IGNORE INTO osrs_roles (osrs_role_id, osrs_role_name) VALUES (%s, %s)",linked)
            #Populate the link table between osrs roles and discord roles
            cursor.execute("""INSERT IGNORE INTO link_discord_osrs_roles (discord_role_id, osrs_role_id)
                SELECT dr.discord_role_id, dpr.promotion_rank_id AS osrs_role_id
                FROM discord_roles AS dr
                JOIN discord_promotion_ranks AS dpr ON dpr.discord_role_id = dr.discord_role_id
                WHERE dpr.promotion_rank_id IS NOT NULL""")
            connection.commit()

        if unlinked:
            # osrs_role_id is being assigned explicitly here, so compute the next free
            # index ourselves rather than relying on auto-increment (avoids colliding
            # with the promotion_rank_id values just inserted above).
            cursor.execute("SELECT COALESCE(MAX(osrs_role_id), 0) FROM osrs_roles")
            next_id = cursor.fetchone()[0] + 1
            unlinked_rows = []
            for role in unlinked:
                unlinked_rows.append((next_id, role))
                next_id += 1
            cursor.executemany(
                "INSERT IGNORE INTO osrs_roles (osrs_role_id, osrs_role_name) VALUES (%s, %s)",
                unlinked_rows
            )
            connection.commit()
        #Get OSRS roles list
        cursor.execute("SELECT osrs_role_name, osrs_role_id FROM osrs_roles")
        rank_map = {row[0]: row[1] for row in cursor.fetchall()}
        return rank_map
    finally:
        cursor.close()

# Insert or Update OSRS (Wise Old Man) group members
def Members_List_And_Roles_List_Update(connection, member_data, member_id=None):
    entries = _normalize_wom(member_data, member_id)
    if not entries:
        return 0
    unique_roles = list({m["role"] for m in member_data["groupData"]["memberships"]})
    print(unique_roles)
    rank_map = _load_rank_map(connection, unique_roles)
    rows = [
        (
            entry["player_id"],
            _text(entry.get("display_name")),
            _resolve_rank_id(entry, rank_map),
            entry.get("created_at"),
        )
        for entry in entries
    ]
    cursor = connection.cursor()
    try:
        sql = """INSERT INTO osrs_members (player_id, current_rsn, rank_id, join_date, current_member)
        VALUES (%s, %s, %s, %s, TRUE)
        ON DUPLICATE KEY UPDATE current_rsn = VALUES(current_rsn), rank_id = VALUES(rank_id), current_member = TRUE, leave_date = NULL"""
        cursor.executemany(sql, rows)
        connection.commit()
        rowcount = cursor.rowcount
    except MySQLError:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return rowcount