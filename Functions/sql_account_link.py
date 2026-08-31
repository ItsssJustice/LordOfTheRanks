#Get linked accounts between discord_id and player_id (accepts single values for either variable, or equal length lists for both inputs for verification)
def Linked_Accounts_Get(SQL_Cursor, discord_id: int = None, player_id: int = None) -> list:
    if discord_id is None and player_id is None:
        raise ValueError("At least one of discord_id or player_id must be provided")

    is_discord_list = isinstance(discord_id, (list, tuple, set))
    is_player_list = isinstance(player_id, (list, tuple, set))

    # Reject a single scalar paired against a list, per spec: lists must
    # either match in length against another list, or the other input
    # must be None entirely.
    if is_discord_list and player_id is not None and not is_player_list:
        raise ValueError("If discord_id is a list, player_id must be either None or a list of the same length")
    if is_player_list and discord_id is not None and not is_discord_list:
        raise ValueError("If player_id is a list, discord_id must be either None or a list of the same length")

    where_clause = ""
    params = []

    if discord_id is not None and player_id is not None:
        # Both provided - pair them up index-by-index. Single values become
        # a one-element list so the pairing logic is uniform.
        d_list = list(discord_id) if is_discord_list else [discord_id]
        p_list = list(player_id) if is_player_list else [player_id]

        if len(d_list) != len(p_list):
            raise ValueError(f"discord_id and player_id lists must be the same length (got {len(d_list)} and {len(p_list)})")
        if not d_list:
            return []

        # Each pair must exist together on the same discord_osrs_link row
        pair_clauses = []
        for d, p in zip(d_list, p_list):
            pair_clauses.append("(l1.discord_id = %s AND l1.player_id = %s)")
            params.extend([d, p])
        where_clause = " OR ".join(pair_clauses)

    elif discord_id is not None:
        d_list = list(discord_id) if is_discord_list else [discord_id]
        if not d_list:
            return []
        placeholders = ", ".join(["%s"] * len(d_list))
        where_clause = f"l1.discord_id IN ({placeholders})"
        params.extend(d_list)

    else:  # player_id is not None
        p_list = list(player_id) if is_player_list else [player_id]
        if not p_list:
            return []
        placeholders = ", ".join(["%s"] * len(p_list))
        where_clause = f"l1.player_id IN ({placeholders})"
        params.extend(p_list)

    # l1 resolves the target discord_id(s) per the rules above.
    # l2 pulls every row sharing each resolved discord_id (the alt list).
    # DISTINCT guards against duplicate rows when l1 matches more than
    # one input against the same discord_id (e.g. two of someone's alts
    # both passed in as player_id's).
    query = f"SELECT DISTINCT l2.discord_id, l2.player_id, l2.is_main_account FROM discord_osrs_link l1 JOIN discord_osrs_link l2 ON l2.discord_id <=> l1.discord_id WHERE {where_clause} ORDER BY l2.is_main_account DESC, l2.player_id ASC;"
    SQL_Cursor.execute(query, params)
    rows = SQL_Cursor.fetchall()
    if rows:
        Linked_Accounts = [
            {
                "discord_id": row["discord_id"],
                "player_id": row["player_id"],
                "is_main_account": bool(row["is_main_account"]),
            }
            for row in rows
        ]
    else:
        Linked_Accounts = None
    return Linked_Accounts