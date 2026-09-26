from Functions import sql_config
from Functions import sql_account_link
import difflib
FUZZY_MATCH_THRESHOLD = 0.6

# Flatten the WOM group payload into a list of membership entries, optionally filtered to one player
def _normalize_wom(member_data, member_id=None):
	if not member_data:
		return []
	memberships = member_data.get("groupData", {}).get("memberships", [])
	if member_id is not None:
		memberships = [m for m in memberships if str(m.get("player_id")) == str(member_id)]
	return memberships

def _normalize(name: str | None) -> str:
	"""Helper to convert names to lowercase with spaces for comparison."""
	if not name:
		return ""
	# Standardize spaces, underscores, and dashes commonly used across Discord/OSRS
	return name.lower().replace("_", " ").replace("-", " ").strip()

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
def _load_rank_map(SQL_Connection, SQL_Cursor, roles: list = None) -> dict:
	rank_map = {
		row["osrs_role_name"]: row["osrs_role_id"]
		for row in Roles_Get(SQL_Cursor)
	}
	roles = [role for role in (roles or []) if role]
	if not roles:
		return rank_map
	missing = [role for role in roles if role not in rank_map]
	if not missing:
		return rank_map
	# Pull every discord role name -> promotion_rank_id pair for case-insensitive matching
	SQL_Query = "SELECT dr.discord_role_name, dpr.promotion_rank_id FROM discord_roles AS dr JOIN discord_promotion_ranks AS dpr ON dpr.discord_role_id = dr.discord_role_id";
	discord_rows = sql_config.Query_Dicts_Get(SQL_Cursor, SQL_Query)
	# Ensure the name verification when comparing OSRS and discord roles are compliant (no spaces, all lowercase comparison)
	discord_rank_lookup = {
		row["discord_role_name"].lower().replace(" ", "_"): row["promotion_rank_id"]
		for row in discord_rows
		if row["promotion_rank_id"] is not None
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
		SQL_Cursor.executemany("INSERT IGNORE INTO osrs_roles (osrs_role_id, osrs_role_name) VALUES (%s, %s)", linked)
		#Populate the link table between osrs roles and discord roles
		SQL_Cursor.execute(
			"""INSERT IGNORE INTO link_discord_osrs_roles (discord_role_id, osrs_role_id)
			   SELECT dr.discord_role_id, dpr.promotion_rank_id AS osrs_role_id
			   FROM discord_roles AS dr
			   JOIN discord_promotion_ranks AS dpr ON dpr.discord_role_id = dr.discord_role_id
			   WHERE dpr.promotion_rank_id IS NOT NULL"""
		)
		SQL_Connection.commit()
	if unlinked:
		# osrs_role_id is being assigned explicitly here, so compute the next free
		# index ourselves rather than relying on auto-increment (avoids colliding
		# with the promotion_rank_id values just inserted above).
		next_id_rows = sql_config.Query_Dicts_Get(SQL_Cursor, "SELECT COALESCE(MAX(osrs_role_id), 0) AS max_id FROM osrs_roles")
		next_id = next_id_rows[0]["max_id"] + 1
		unlinked_rows = []
		for role in unlinked:
			unlinked_rows.append((next_id, role))
			next_id += 1
		SQL_Cursor.executemany("INSERT IGNORE INTO osrs_roles (osrs_role_id, osrs_role_name) VALUES (%s, %s)", unlinked_rows)
		SQL_Connection.commit()
	#Get OSRS roles list
	rank_map = {
		row["osrs_role_name"]: row["osrs_role_id"]
		for row in Roles_Get(SQL_Cursor)
	}
	return rank_map

# Insert or Update OSRS (Wise Old Man) group members
def Members_List_And_Roles_List_Update(SQL_Connection, SQL_Cursor, member_data, member_id=None):
	entries = _normalize_wom(member_data, member_id)
	if not entries:
		return 0
	unique_roles = list({m["role"] for m in member_data["groupData"]["memberships"]})
	print(unique_roles)
	rank_map = _load_rank_map(SQL_Connection, SQL_Cursor, unique_roles)
	rows = [
		(
			entry["player_id"],
			_text(entry.get("display_name")),
			_resolve_rank_id(entry, rank_map),
			entry.get("created_at"),
		)
		for entry in entries
	]
	cursor = SQL_Connection.cursor()
	try:
		sql = "INSERT INTO osrs_members (player_id, current_rsn, rank_id, join_date, current_member) VALUES (%s, %s, %s, %s, TRUE) ON DUPLICATE KEY UPDATE current_rsn = VALUES(current_rsn), rank_id = VALUES(rank_id), current_member = TRUE"
		cursor.executemany(sql, rows)
		rowcount = cursor.rowcount
		# member_data["groupData"]["memberships"] is always WOM's full group roster, regardless
		# of member_id (which only narrows `entries`/`rows` above) - so anyone in the database
		# marked current_member = TRUE who isn't in that full list has left the clan.
		All_Present_Player_Ids = [m["player_id"] for m in member_data["groupData"]["memberships"]]
		Placeholders = ", ".join(["%s"] * len(All_Present_Player_Ids))
		Absent_Sql = ("UPDATE osrs_members SET current_member = FALSE WHERE current_member = TRUE AND player_id NOT IN (%s)" % Placeholders)
		cursor.execute(Absent_Sql, tuple(All_Present_Player_Ids))
		SQL_Connection.commit()
	except MySQLError:
		SQL_Connection.rollback()
		raise
	finally:
		cursor.close()
	return rowcount

#Get all osrs members
def Members_Get(SQL_Cursor) -> list[dict]:
	Query = "SELECT player_id, current_rsn, rank_id, join_date, leave_date, current_member, created_at, updated_at FROM osrs_members"
	'''Query = """SELECT om.player_id, om.current_rsn, om.rank_id, om.join_date, om.leave_date, om.current_member, om.created_at, om.updated_at, dpr.promotion_rank_id AS discord_promotion_rank_id FROM osrs_members AS om
	LEFT JOIN link_discord_osrs_roles AS ldo ON om.rank_id = ldo.osrs_role_id
	LEFT JOIN discord_promotion_roles AS dpr ON ldo.discord_role_id = dpr.discord_role_id"""'''
	return sql_config.Query_Dicts_Get(SQL_Cursor, Query)

#Display all osrs members
def Members_Display(members: list[dict]):
	"""Prints osrs_members formatted in the console."""
	print(f"\n--- OSRS MEMBERS ({len(members)} records) ---")
	header = f"{'Player ID':<10} | {'Current RSN':<20} | {'Rank ID':<8} | {'Active':<7} | {'Join Date'}"
	print(header)
	print("-" * len(header))
	for m in members:
		join_str = m['join_date'].strftime('%Y-%m-%d') if m['join_date'] else 'N/A'
		print(
			f"{str(m['player_id']):<10} | "
			f"{str(m['current_rsn']):<20} | "
			f"{str(m['rank_id']):<8} | "
			f"{str(m['current_member']):<7} | "
			f"{join_str}"
		)

#Retrieves every row of osrs_roles (osrs_role_id, osrs_role_name).
def Roles_Get(SQL_Cursor) -> list[dict]:
	Query = "SELECT osrs_role_id, osrs_role_name FROM osrs_roles"
	return sql_config.Query_Dicts_Get(SQL_Cursor, Query)

# How close a typed RSN has to be to a real one before it is treated as a match
# at all. Below this, a wildly different name should fail rather than silently
# link to whichever row happens to score highest.
def _similarity(a: str, b: str) -> float:
	"""0..1 similarity between two already-normalized names."""
	return difflib.SequenceMatcher(None, a, b).ratio()

# Resolve a typed RSN to the player_id it most likely names, for /linked_accounts commands.
# Exact (normalized) matches always win outright. Failing that, the closest match by
# similarity is used provided it clears FUZZY_MATCH_THRESHOLD - a typo like "zezzima"
# still resolves to "zezima" rather than forcing an exact re-type.
def Runescape_Name_To_Player_ID(SQL_Cursor, runescape_name: str, discord_id: int = None, Require_Unlinked: bool = True, Own_Only: bool = False):
	"""
	Resolve an RSN to a player_id by fuzzy-matching current_rsn.
	Own_Only controls the search scope:
	  False (default): searches the whole osrs_members roster - the RSN need
	      not be linked to anyone yet. Used for linking/updating a link.
	      discord_id, if given, is only used for the Require_Unlinked check
	      below (does the match belong to THIS discord_id already).
	  True: searches only accounts already linked to discord_id (required in
	      this mode) - never touches an unlinked account or someone else's.
	      Used for commands that must only ever act on an existing link of the
	      caller's own, e.g. set_main_rsn.
	Returns:
		int    the player_id
		None   Own_Only=False only: no RSN this close matches anyone at all
		False  Own_Only=False: a match was found, but Require_Unlinked=True and
		       it's already linked to a different discord_id than supplied
		       Own_Only=True: no linked account of discord_id's has a close
		       enough RSN (including having none linked at all) - "not found"
		       and "not yours" collapse into the same outcome here, since
		       Own_Only never looks past the caller's own links to tell them
		       apart in the first place.
	"""
	from Functions import sql_account_link   # local import: avoids a top-level circular import with sql_account_link.py
	Not_Found = False if Own_Only else None
	Wanted = _normalize(runescape_name)
	if not Wanted:
		return Not_Found
	if Own_Only:
		if discord_id is None:
			return False
		Own_Links = sql_account_link.Linked_Accounts_Get(SQL_Cursor, discord_id=discord_id, player_id=None) or []
		if not Own_Links:
			return False
		Own_Player_Ids = {L["player_id"] for L in Own_Links}
		Candidate_Rows = [R for R in (Members_Get(SQL_Cursor) or []) if R["player_id"] in Own_Player_Ids]
	else:
		Candidate_Rows = Members_Get(SQL_Cursor) or []
	if not Candidate_Rows:
		return Not_Found
	Scored = sorted(((_similarity(Wanted, _normalize(R["current_rsn"])), R) for R in Candidate_Rows), key=lambda Pair: Pair[0],	reverse=True)
	Best_Score, Best_Row = Scored[0]
	if Best_Score < FUZZY_MATCH_THRESHOLD:
		return Not_Found
	Player_Id = Best_Row["player_id"]
	if Own_Only:
		return Player_Id  # already confirmed above to be one of discord_id's own links
	if Require_Unlinked:
		Existing_Links = sql_account_link.Linked_Accounts_Get(SQL_Cursor, discord_id=None, player_id=Player_Id)
		if Existing_Links:
			Existing_Discord_Id = Existing_Links[0]["discord_id"]
			if discord_id is None or int(Existing_Discord_Id) != int(discord_id):
				return False
	return Player_Id