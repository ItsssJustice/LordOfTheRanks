from Functions import sql_config
from Functions import sql_account_osrs
from Functions import sql_account_discord
from Functions import bot_config

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
def Linked_Accounts_Attempt_Matches(SQL_Cursor, discord_members: list[dict], osrs_members: list[dict]) -> dict[str, list[dict]]:
	# Fetch supporting tables, falling back to empty lists if None
	known_links = Linked_Accounts_Get(SQL_Cursor) or []
	osrs_roles = sql_account_osrs.Roles_Get(SQL_Cursor) or []
	discord_promotion_ranks = sql_account_discord.Promotion_Ranks_Get(SQL_Cursor) or []
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
	# 2. rank_id -> osrs_roles.osrs_role_id (confirms it's a genuine, known role), then compared
	#    directly against discord_promotion_ranks.promotion_rank_id to see if that rank is one
	#    discord_promotion_ranks actually recognises as a potential promotion rank.
	osrs_role_by_id = {r['osrs_role_id']: r for r in osrs_roles}
	valid_promotion_rank_ids = {r['promotion_rank_id'] for r in discord_promotion_ranks}
	def _has_promotable_rank(player_id: int) -> bool:
		osrs = osrs_by_id.get(player_id)
		if not osrs:
			return False
		rank_id = osrs.get('rank_id')
		if rank_id not in osrs_role_by_id:
			return False
		return rank_id in valid_promotion_rank_ids
	# 3. Compute matches based on _normalized name comparisons
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
	# 4. Initialize results buckets
	strong_matches = []      # 1. Resolved match(es), main account determined
	conflicts = []           # 2. Ambiguous/indeterminate match
	unmatched_discord = []   # 3. Discord users with no OSRS match/link
	unmatched_osrs = []      # 4. OSRS users with no Discord match/link
	repaired_needed = []     # 5. Known links where name comparison no longer matches
	# Helper tracking
	processed_players = set()
	processed_discords = set()
	# --- CATEGORY 5: Needs Repair ---
	# Keeps whatever is_main_account value the existing link already has - repair is about the
	# name no longer matching, not about recomputing main-account status.
	for link in known_links:
		d_id = link['discord_id']
		p_id = link['player_id']
		if d_id and d_id in discord_by_id and p_id in osrs_by_id:
			matches_for_player = candidate_matches.get(p_id, set())
			if d_id not in matches_for_player:
				repaired_needed.append({
					"discord_id": d_id,
					"player_id": p_id,
					"is_main_account": bool(link.get('is_main_account', False)),
					"reason": "Name mismatch on known link"
				})
				processed_players.add(p_id)
				processed_discords.add(d_id)
	# --- Split candidate_matches into "clean" single-discord players vs ambiguous multi-discord players ---
	# CATEGORY 2a: a single OSRS RSN matched more than one Discord entry - can't tell which Discord
	# account is theirs, so this can't be resolved into a main-account decision at all.
	single_discord_players: dict[int, int] = {}  # player_id -> discord_id
	for p_id, matched_discords in candidate_matches.items():
		if p_id in processed_players:
			continue
		if len(matched_discords) > 1:
			for d_id in matched_discords:
				conflicts.append({
					"discord_id": d_id,
					"player_id": p_id,
					"is_main_account": False,
					"reason": "Multiple Discord matches found for single RSN"
				})
			processed_players.add(p_id)
		else:
			single_discord_players[p_id] = next(iter(matched_discords))
	# --- Group the remaining clean matches by Discord entry ---
	discord_to_players: dict[int, list[int]] = {}
	for p_id, d_id in single_discord_players.items():
		discord_to_players.setdefault(d_id, []).append(p_id)
	# --- CATEGORY 1 & 2b: Strong matches vs conflicts, resolved via promotion rank ---
	for d_id, players in discord_to_players.items():
		if d_id in processed_discords:
			continue
		players = [p for p in players if p not in processed_players]
		if not players:
			continue
		if len(players) == 1:
			# Single OSRS account for this Discord entry - main-account status still follows
			# whether the account holds a rank recognised in valid_promotion_rank_ids, rather
			# than being automatically True just because there's no other candidate.
			p_id = players[0]
			strong_matches.append({
				"discord_id": d_id,
				"player_id": p_id,
				"is_main_account": _has_promotable_rank(p_id)
			})
			processed_players.add(p_id)
			processed_discords.add(d_id)
			continue
		# Multiple OSRS accounts matched to a single Discord entry - use the rank/role chain to
		# find whichever account(s) hold a rank that discord_promotion_ranks recognises.
		promotable = [p for p in players if _has_promotable_rank(p)]
 
		if len(promotable) == 1:
			main_p = promotable[0]
			for p_id in players:
				strong_matches.append({
					"discord_id": d_id,
					"player_id": p_id,
					"is_main_account": p_id == main_p
				})
				processed_players.add(p_id)
			processed_discords.add(d_id)
		else:
			# Either no account or more than one account qualifies - can't determine a main account
			reason = (
				"No matched account holds a recognised promotion rank"
				if not promotable else
				"Multiple matched accounts hold a recognised promotion rank"
			)
			for p_id in players:
				conflicts.append({
					"discord_id": d_id,
					"player_id": p_id,
					"is_main_account": False,
					"reason": reason
				})
				processed_players.add(p_id)
			processed_discords.add(d_id)
	# --- CATEGORY 3: Unmatched Discord ---
	for disc in discord_members:
		d_id = disc['discord_id']
		if d_id not in processed_discords and d_id not in linked_discord_to_player:
			unmatched_discord.append({"discord_id": d_id, "player_id": None, "is_main_account": False})
	# --- CATEGORY 4: Unmatched OSRS ---
	for osrs in osrs_members:
		p_id = osrs['player_id']
		if p_id not in processed_players and p_id not in linked_player_to_discords:
			unmatched_osrs.append({"discord_id": None, "player_id": p_id, "is_main_account": _has_promotable_rank(p_id)})
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
		print(f"{'#':<4} | {'OSRS Player':<35} | {'Discord User':<35} | {'Main?':<5} | {'Notes / Reason'}")
		print("-" * 105)
		for idx, item in enumerate(records, 1):
			p_id = item.get("player_id")
			osrs_str = get_osrs_label(p_id)
			# Special handling for conflicts where multiple Discord IDs exist
			if "discord_ids" in item:
				disc_str = ", ".join(get_disc_label(d_id) for d_id in item["discord_ids"])
			else:
				disc_str = get_disc_label(item.get("discord_id"))
			main_str = "Yes" if item.get("is_main_account") else "No"
			reason = item.get("reason", "")
			print(f"{idx:<4} | {osrs_str:<35} | {disc_str:<35} | {main_str:<5} | {reason}")

async def Linked_Accounts_Attempt_Match_Strong_Update(SQL_Connection, SQL_Cursor, categorized_data: dict[str, list[dict]], discord_members: list[dict], osrs_members: list[dict]):
	# Define metadata for printing each section
	sections = [
		("STRONG MATCHES", "strong_matches"),
	]
	for title, key in sections:
		records = categorized_data.get(key, [])
		if not records:
			continue
		for idx, item in enumerate(records, 1):
			await Linked_Accounts_Update(SQL_Connection, SQL_Cursor, item.get("discord_id"), item.get("player_id"), item.get("is_main_account"), None)

#Check whether a discord_id is moderator-locked. One row per discord_id in the
#lock table, so this is always a single-row lookup regardless of how many OSRS
#accounts that Discord user has linked.
def Moderator_Locked_Get(SQL_Cursor, discord_id) -> bool:
	Query = "SELECT moderator_locked FROM link_discord_osrs_members_moderator_locked WHERE discord_id = %s"
	SQL_Cursor.execute(Query, (discord_id,))
	Row = SQL_Cursor.fetchone()
	return bool(Row[0]) if Row else False

#Set the moderator lock for a discord_id. discord_id is the primary key on this
#table, so this is a single upsert - it never touches per-link rows at all.
def Moderator_Locked_Set(SQL_Cursor, discord_id, locked: bool):
	Query = """INSERT INTO link_discord_osrs_members_moderator_locked (discord_id, moderator_locked)
	           VALUES (%s, %s) ON DUPLICATE KEY UPDATE moderator_locked = VALUES(moderator_locked)"""
	SQL_Cursor.execute(Query, (discord_id, locked))

#Get linked accounts between discord_id and player_id (accepts single values or lists for either variable)
def Linked_Accounts_Get(SQL_Cursor, discord_id: int | list = None, player_id: int | list = None, For_Update: bool = False) -> list:
	is_discord_list = isinstance(discord_id, (list, tuple, set))
	is_player_list = isinstance(player_id, (list, tuple, set))
	d_list = list(discord_id) if is_discord_list else ([discord_id] if discord_id is not None else None)
	p_list = list(player_id) if is_player_list else ([player_id] if player_id is not None else None)
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
	where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
	Query = f"""
		SELECT DISTINCT l2.link_id, l2.discord_id, l2.player_id, l2.is_main_account,
		       COALESCE(mlock.moderator_locked, FALSE) AS moderator_locked
		FROM link_discord_osrs_members l1 
		JOIN link_discord_osrs_members l2 ON l2.discord_id <=> l1.discord_id 
		LEFT JOIN link_discord_osrs_members_moderator_locked mlock ON mlock.discord_id = l2.discord_id
		{where_sql} 
		ORDER BY l2.is_main_account DESC, l2.player_id ASC
	"""
	if For_Update:
		Query += " FOR UPDATE"
	Query += ";"
	rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, tuple(params))
	if rows:
		return [
			{
				"link_id": row["link_id"],
				"discord_id": row["discord_id"],
				"player_id": row["player_id"],
				"is_main_account": bool(row["is_main_account"]),
				"moderator_locked": bool(row["moderator_locked"]),
			}
			for row in rows
		]
	return None

#Create or update a discord to osrs link
async def Linked_Accounts_Update(SQL_Connection, SQL_Cursor, discord_id, osrs_id, is_main_account, caller_id=None):
	"""
	Returns:
		int    the link_id on success (existing link updated, or new one created)
		None   discord_id/osrs_id were not valid positive integers
		"permission_denied"  caller_id may not modify this discord_id's links
		"owned_by_another"   osrs_id is already linked to a different discord_id
		"locked"              the account is moderator-locked
	"""
	DISCORD_USER = bot_config.env_get("DISCORD_USER")
	try:
		discord_id = int(discord_id)
		osrs_id = int(osrs_id)
		is_main_account = bool(is_main_account)
	except (TypeError, ValueError):
		return None
	if discord_id <= 0 or osrs_id <= 0:
		return None
	caller_id = caller_id if caller_id is not None else DISCORD_USER
	is_moderator = sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, caller_id, 1)
	modifying_another_user = caller_id != discord_id
	if caller_id != DISCORD_USER and modifying_another_user and not is_moderator:
		return "permission_denied"
	try:
		if SQL_Connection.in_transaction:
			SQL_Connection.commit()
		SQL_Connection.start_transaction()
		existing_links = Linked_Accounts_Get(SQL_Cursor, discord_id, player_id=None, For_Update=True) or []
		existing_player_link_rows = Linked_Accounts_Get(SQL_Cursor, discord_id=None, player_id=osrs_id, For_Update=True) or []
		existing_player_link = next((row for row in existing_player_link_rows if row["player_id"] == osrs_id), None)
		if existing_player_link:
			existing_player_discord_id = existing_player_link["discord_id"]
			if existing_player_discord_id != discord_id:
				SQL_Connection.rollback()
				return "owned_by_another"
		# Single-row lookup against the lock table, instead of scanning every row
		# in existing_links for a moderator_locked flag that used to be repeated
		# on each of them.                                                       # CHANGED
		account_locked = Moderator_Locked_Get(SQL_Cursor, discord_id)            # CHANGED
		if account_locked and not is_moderator and caller_id != DISCORD_USER:
			SQL_Connection.rollback()
			return "locked"
		if existing_player_link:
			link_id = existing_player_link["link_id"]
			if len(existing_links) == 1:
				is_main_account = True
			if is_main_account:
				Update_Query = "UPDATE link_discord_osrs_members SET is_main_account = FALSE WHERE discord_id = %s"
				SQL_Cursor.execute(Update_Query, (discord_id,))
			Update_Query = "UPDATE link_discord_osrs_members SET is_main_account = %s WHERE link_id = %s AND discord_id = %s"
			SQL_Cursor.execute(Update_Query, (is_main_account, link_id, discord_id))
			SQL_Connection.commit()
			return link_id
		if not existing_links:
			is_main_account = True
		elif is_main_account:
			Update_Query = "UPDATE link_discord_osrs_members SET is_main_account = FALSE WHERE discord_id = %s"
			SQL_Cursor.execute(Update_Query, (discord_id,))
		Insert_Query = "INSERT INTO link_discord_osrs_members (discord_id,player_id,is_main_account) VALUES (%s, %s, %s)"
		SQL_Cursor.execute(Insert_Query, (discord_id, osrs_id, is_main_account))
		link_id = SQL_Cursor.lastrowid
		SQL_Connection.commit()
		return link_id
	except Exception:
		SQL_Connection.rollback()
		raise

# Flip which of a Discord user's already-linked OSRS accounts is flagged main.
# Never creates or deletes a link - it only ever toggles is_main_account on one
# that discord_id already owns.
async def Linked_Accounts_Set_Main(SQL_Connection, SQL_Cursor, discord_id, osrs_id, caller_id):
	"""
	Returns:
		int    the link_id now flagged main, on success
		None   discord_id/osrs_id were not valid positive integers
		"permission_denied"  caller may not modify this discord_id's links
		"not_found"           osrs_id is not one of discord_id's linked accounts
		"already_main"        osrs_id is already discord_id's main account
		"locked"              the account is moderator-locked, and caller is not a moderator
	"""
	try:
		discord_id = int(discord_id)
		osrs_id = int(osrs_id)
	except (TypeError, ValueError):
		return None
	if discord_id <= 0 or osrs_id <= 0:
		return None
	is_moderator = sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, caller_id, 1)
	modifying_another_user = caller_id != discord_id
	if modifying_another_user and not is_moderator:
		return "permission_denied"
	try:
		if SQL_Connection.in_transaction:
			SQL_Connection.commit()
		SQL_Connection.start_transaction()
		if not is_moderator and Moderator_Locked_Get(SQL_Cursor, discord_id):
			SQL_Connection.rollback()
			return "locked"
		existing_links = Linked_Accounts_Get(SQL_Cursor, discord_id=discord_id, player_id=None, For_Update=True) or []
		target_link = next((row for row in existing_links if row["player_id"] == osrs_id), None)
		if not target_link:
			SQL_Connection.rollback()
			return "not_found"
		if target_link["is_main_account"]:
			SQL_Connection.rollback()
			return "already_main"
		Update_Query = "UPDATE link_discord_osrs_members SET is_main_account = FALSE WHERE discord_id = %s"
		SQL_Cursor.execute(Update_Query, (discord_id,))
		Update_Query = "UPDATE link_discord_osrs_members SET is_main_account = TRUE WHERE link_id = %s AND discord_id = %s"
		SQL_Cursor.execute(Update_Query, (target_link["link_id"], discord_id))
		SQL_Connection.commit()
		return target_link["link_id"]
	except Exception:
		SQL_Connection.rollback()
		raise

# Delete an OSRS-discord account link
async def Linked_Accounts_Delete(SQL_Connection, SQL_Cursor, discord_id, osrs_id, caller_id):
	"""
	Returns:
		int    the deleted link_id on success
		None   discord_id/osrs_id were not valid positive integers
		"permission_denied"  caller may not modify this discord_id's links
		"not_found"           no such link exists
		"final_account"       this is the member's only linked account, and caller is not a moderator
		"locked"              the account is moderator-locked, and caller is not a moderator
	"""
	try:
		discord_id = int(discord_id)
		osrs_id = int(osrs_id)
	except (TypeError, ValueError):
		return None
	if discord_id <= 0 or osrs_id <= 0:
		return None
	is_moderator = sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, caller_id, 1)
	modifying_another_user = caller_id != discord_id
	if modifying_another_user and not is_moderator:
		return "permission_denied"
	try:
		if SQL_Connection.in_transaction:
			SQL_Connection.commit()
		SQL_Connection.start_transaction()
		# Single-row lock check, done up front rather than derived from the linked
		# rows fetched below - this also means a locked account with zero links
		# left can't be re-touched by its owner, which the old per-row check on
		# existing_links could never express since it had nothing to read.       # CHANGED
		if not is_moderator and Moderator_Locked_Get(SQL_Cursor, discord_id):    # CHANGED
			SQL_Connection.rollback()                                            # CHANGED
			return "locked"                                                      # CHANGED
		existing_links = Linked_Accounts_Get(SQL_Cursor, discord_id=discord_id, player_id=None, For_Update=True)
		if not existing_links:
			SQL_Connection.rollback()
			return "not_found"
		target_link = next((row for row in existing_links if row["player_id"] == osrs_id), None)
		if not target_link:
			SQL_Connection.rollback()
			return "not_found"
		if len(existing_links) <= 1 and not is_moderator:
			SQL_Connection.rollback()
			return "final_account"
		link_id = target_link["link_id"]
		was_main = bool(target_link["is_main_account"])
		Delete_Query = "DELETE FROM link_discord_osrs_members WHERE link_id = %s AND discord_id = %s AND player_id = %s"
		SQL_Cursor.execute(Delete_Query, (link_id, discord_id, osrs_id))
		if SQL_Cursor.rowcount != 1:
			SQL_Connection.rollback()
			return None
		if was_main:
			remaining_links = Linked_Accounts_Get(SQL_Cursor, discord_id=discord_id, player_id=None, For_Update=True)
			if remaining_links:
				new_main_link_id = remaining_links[0]["link_id"]
				Update_Query = "UPDATE link_discord_osrs_members SET is_main_account = TRUE WHERE link_id = %s"
				SQL_Cursor.execute(Update_Query, (new_main_link_id,))
		SQL_Connection.commit()
		return link_id
	except Exception:
		SQL_Connection.rollback()
		raise

# Toggle moderator_locked for a Discord user. Single upsert against the lock table
async def Linked_Accounts_Lock_Toggle(SQL_Connection, SQL_Cursor, discord_id, caller_id):
	"""
	Returns:
		"locked" / "unlocked"  the new state, on success
		None                    discord_id was not a valid positive integer
		"permission_denied"    caller is not a moderator
		"not_found"             the member has no linked accounts
	"""
	try:
		discord_id = int(discord_id)
	except (TypeError, ValueError):
		return None
	if discord_id <= 0:
		return None
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, caller_id, 1):
		return "permission_denied"
	try:
		if SQL_Connection.in_transaction:
			SQL_Connection.commit()
		SQL_Connection.start_transaction()
		#existing_links = Linked_Accounts_Get(SQL_Cursor, discord_id=discord_id, player_id=None, For_Update=True)
		#if not existing_links:
			#SQL_Connection.rollback()
			#return "not_found"
		currently_locked = Moderator_Locked_Get(SQL_Cursor, discord_id)
		# No row yet for this discord_id -> default action is to add the entry and lock it, rather than toggling an assumed "unlocked" state
		if currently_locked is None:
			new_lock_state = True
		else:
			new_lock_state = not currently_locked
		Moderator_Locked_Set(SQL_Cursor, discord_id, new_lock_state)
		SQL_Connection.commit()
		return "locked" if new_lock_state else "unlocked"
	except Exception:
		SQL_Connection.rollback()
		raise