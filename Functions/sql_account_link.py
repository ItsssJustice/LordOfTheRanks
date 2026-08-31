def _normalize(name: str | None) -> str:
	"""Helper to convert names to lowercase with spaces for comparison."""
	if not name:
		return ""
	# Standardize spaces, underscores, and dashes commonly used across Discord/OSRS
	return name.lower().replace("_", " ").replace("-", " ").strip()


#Compares osrs_members.current_rsn against all discord name fields, returns lists based on match criteria:
# - Strong matches
# - Indeterminate conflicts
# - Unmatched discord
# - Unmatched osrs
# - Repair needed
def Linked_Accounts_Attempt_Matches(discord_members: list[dict], osrs_members: list[dict], known_links: list[dict]) -> dict[str, list[dict]]:
	# Fallback to an empty list if known_links is None
	known_links = known_links or []
	
	# 1. Build lookup tables for existing links
	linked_discord_to_player = {
		link['discord_id']: link['player_id'] 
		for link in known_links if link['discord_id'] is not None
	}
	linked_player_to_discords = {}
	for link in known_links:
		if link['discord_id'] is not None:
			linked_player_to_discords.setdefault(link['player_id'], set()).add(link['discord_id'])

	# Fast maps for members
	osrs_by_id = {o['player_id']: o for o in osrs_members}
	discord_by_id = {d['discord_id']: d for d in discord_members}

	# 2. Compute matches based on _normalized name comparisons
	candidate_matches: dict[int, set[int]] = {}  # player_id -> set of discord_ids
	
	for osrs in osrs_members:
		p_id = osrs['player_id']
		rsn_norm = _normalize(osrs['current_rsn'])
		if not rsn_norm:
			continue
			
		for disc in discord_members:
			d_id = disc['discord_id']
			# Match against all four Discord name fields
			disc_names = {
				_normalize(disc['name_user']),
				_normalize(disc['name_global']),
				_normalize(disc['name_display']),
				_normalize(disc['name_nick'])
			} - {""}

			if rsn_norm in disc_names:
				candidate_matches.setdefault(p_id, set()).add(d_id)

	# 3. Initialize results buckets
	strong_matches = []      # 1. Single strong match found
	conflicts = []           # 2. Ambiguous/indeterminate match (1 player -> multi Discord or vice versa)
	unmatched_discord = []   # 3. Discord users with no OSRS match/link
	unmatched_osrs = []      # 4. OSRS users with no Discord match/link
	repaired_needed = []     # 5. Known links where name comparison no longer matches

	# Helper tracking
	processed_players = set()
	processed_discords = set()

	# --- CATEGORY 5: Needs Repair ---
	for link in known_links:
		d_id = link['discord_id']
		p_id = link['player_id']
		if d_id and d_id in discord_by_id and p_id in osrs_by_id:
			# Check if name match is broken
			matches_for_player = candidate_matches.get(p_id, set())
			if d_id not in matches_for_player:
				repaired_needed.append({
					"discord_id": d_id,
					"player_id": p_id,
					"current_rsn": osrs_by_id[p_id]['current_rsn'],
					"reason": "Name mismatch on known link"
				})
				processed_players.add(p_id)
				processed_discords.add(d_id)

	# --- CATEGORY 1 & 2: Strong Matches vs Conflicts ---
	for p_id, matched_discords in candidate_matches.items():
		if p_id in processed_players:
			continue
			
		if len(matched_discords) == 1:
			d_id = list(matched_discords)[0]
			if d_id not in processed_discords:
				strong_matches.append({"discord_id": d_id, "player_id": p_id})
				processed_players.add(p_id)
				processed_discords.add(d_id)
			else:
				# Discord ID was already matched to a different player
				conflicts.append({
					"player_id": p_id,
					"discord_ids": list(matched_discords),
					"reason": "Discord ID claimed by another player"
				})
				processed_players.add(p_id)
		else:
			# 1 OSRS player matched multiple Discord accounts
			conflicts.append({
				"player_id": p_id,
				"discord_ids": list(matched_discords),
				"reason": "Multiple Discord matches found for single RSN"
			})
			processed_players.add(p_id)

	# --- CATEGORY 3: Unmatched Discord ---
	for disc in discord_members:
		d_id = disc['discord_id']
		if d_id not in processed_discords and d_id not in linked_discord_to_player:
			unmatched_discord.append({"discord_id": d_id, "player_id": None})

	# --- CATEGORY 4: Unmatched OSRS ---
	for osrs in osrs_members:
		p_id = osrs['player_id']
		if p_id not in processed_players and p_id not in linked_player_to_discords:
			unmatched_osrs.append({"discord_id": None, "player_id": p_id})

	return {
		"strong_matches": strong_matches,
		"conflicts": conflicts,
		"unmatched_discord": unmatched_discord,
		"unmatched_osrs": unmatched_osrs,
		"repaired_needed": repaired_needed
	}

#Display formatted tables for the attempted account linkages
def Linked_Accounts_Attempt_Match_Display(categorized_data: dict[str, list[dict]], discord_members: list[dict], osrs_members: list[dict]):
	# Build quick lookup dictionaries for names
	disc_lookup = {d["discord_id"]: d for d in discord_members}
	osrs_lookup = {o["player_id"]: o for o in osrs_members}

	def get_disc_label(d_id: int | None) -> str:
		if d_id is None or d_id not in disc_lookup:
			return "N/A"
		# Prefers display name, falling back to global/username
		m = disc_lookup[d_id]
		name = m.get("name_display") or m.get("name_nick") or m.get("name_global") or m.get("name_user")
		return f"({d_id}) {name}"

	def get_osrs_label(p_id: int | None) -> str:
		if p_id is None or p_id not in osrs_lookup:
			return "N/A"
		m = osrs_lookup[p_id]
		return f"({p_id}) {m.get('current_rsn', 'N/A')}"

	# Define metadata for printing each section
	sections = [
		("STRONG MATCHES", "strong_matches"),
		("CONFLICTS (INDETERMINATE MATCHES)", "conflicts"),
		("UNMATCHED DISCORD USERS", "unmatched_discord"),
		("UNMATCHED OSRS PLAYERS", "unmatched_osrs"),
		("NEEDS REPAIR (CHANGED MATCHES)", "repaired_needed"),
	]

	for title, key in sections:
		records = categorized_data.get(key, [])
		print(f"\n==================================================")
		print(f" {title} ({len(records)} records)")
		print(f"==================================================")

		if not records:
			print("  (None)")
			continue

		print(f"{'#':<4} | {'OSRS Player':<35} | {'Discord User':<35} | {'Notes / Reason'}")
		print("-" * 105)

		for idx, item in enumerate(records, 1):
			p_id = item.get("player_id")
			osrs_str = get_osrs_label(p_id)
			
			# Special handling for conflicts where multiple Discord IDs exist
			if "discord_ids" in item:
				disc_str = ", ".join(get_disc_label(d_id) for d_id in item["discord_ids"])
			else:
				disc_str = get_disc_label(item.get("discord_id"))

			reason = item.get("reason", "")
			
			print(f"{idx:<4} | {osrs_str:<35} | {disc_str:<35} | {reason}")

# Get linked accounts between discord_id and player_id (accepts single values or lists for either variable)
def Linked_Accounts_Get(SQL_Cursor, discord_id: int | list = None, player_id: int | list = None) -> list:
	if discord_id is None and player_id is None:
		raise ValueError("At least one of discord_id or player_id must be provided")

	is_discord_list = isinstance(discord_id, (list, tuple, set))
	is_player_list = isinstance(player_id, (list, tuple, set))

	# Normalize inputs into lists for uniform SQL generation
	d_list = list(discord_id) if is_discord_list else ([discord_id] if discord_id is not None else None)
	p_list = list(player_id) if is_player_list else ([player_id] if player_id is not None else None)

	# Return early if any provided list is empty
	if (d_list is not None and not d_list) or (p_list is not None and not p_list):
		return None

	where_clauses = []
	params = []

	if d_list is not None:
		placeholders = ", ".join(["%s"] * len(d_list))
		where_clauses.append(f"l1.discord_id IN ({placeholders})")
		params.extend(d_list)

	if p_list is not None:
		placeholders = ", ".join(["%s"] * len(p_list))
		where_clauses.append(f"l1.player_id IN ({placeholders})")
		params.extend(p_list)

	# Combining with AND ensures only rows matching both sets of inputs are returned
	where_sql = " AND ".join(where_clauses)

	query = f"""
		SELECT DISTINCT l2.discord_id, l2.player_id, l2.is_main_account 
		FROM link_discord_osrs_members l1 
		JOIN link_discord_osrs_members l2 ON l2.discord_id <=> l1.discord_id 
		WHERE {where_sql} 
		ORDER BY l2.is_main_account DESC, l2.player_id ASC;
	"""

	SQL_Cursor.execute(query, params)
	rows = SQL_Cursor.fetchall()

	if rows:
		return [
			{
				"discord_id": row["discord_id"],
				"player_id": row["player_id"],
				"is_main_account": bool(row["is_main_account"]),
			}
			for row in rows
		]
	return None