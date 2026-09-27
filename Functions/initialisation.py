import datetime
import discord
from Functions import sql_config
from Functions import sql_points

#bot_config flag that gates the one-off initial setup actions
INITIAL_CONFIGURATION_CONFIG_NAME = "initial_configuration_complete"
#Points source each monthly membership token is recorded against ("Clan Membership"), and the points_values level used for its value
MEMBERSHIP_POINTS_SOURCE_ID = 3
MEMBERSHIP_POINTS_CONTRIBUTION_LEVEL = 1
#Points source the per-user rank top-up tokens are recorded against
RANK_TOP_UP_POINTS_SOURCE_ID = 1

#SQL Query for reading a single bot_config value by name
def Config_Get(SQL_Cursor, config_name):
	sql = "SELECT config_value FROM bot_config WHERE config_name = %s"
	SQL_Cursor.execute(sql, (config_name,))
	row = SQL_Cursor.fetchone()
	if row is None:
		return None
	return row[0]

#SQL Query for setting a single bot_config value by name
def Config_Set(SQL_Connection, SQL_Cursor, config_name, config_value):
	sql = "UPDATE bot_config SET config_value = %s, config_update_time = NOW() WHERE config_name = %s"
	try:
		SQL_Cursor.execute(sql, (config_value, config_name))
		SQL_Connection.commit()
	except Exception as Error:
		SQL_Connection.rollback()
		print("SQL : Config_Set failed for '%s' : %r" % (config_name, Error))
		return None
	print("SQL : bot_config '%s' set to %s" % (config_name, config_value))
	return SQL_Cursor.rowcount

#SQL Query for every linked OSRS account still in the clan (current_member = FALSE accounts are not members), keyed by the owning discord user
#Only discord users with a discord_members row are returned, since that row is where their starting points are recorded
def Linked_Current_Members_Get(SQL_Cursor):
	sql = """SELECT link.discord_id, om.player_id, om.join_date
		FROM link_discord_osrs_members AS link
		INNER JOIN osrs_members AS om ON om.player_id = link.player_id
		INNER JOIN discord_members AS dm ON dm.discord_id = link.discord_id
		WHERE link.discord_id IS NOT NULL AND link.discord_id <> 0 AND om.current_member = TRUE AND om.join_date IS NOT NULL"""
	return sql_config.Query_Dicts_Get(SQL_Cursor, sql)

#SQL Query for the discord users who have already had their starting points assigned
def Initial_Assigned_Get(SQL_Cursor):
	sql = "SELECT discord_id FROM discord_members WHERE initial_points_assigned_at IS NOT NULL"
	Rows = sql_config.Query_Dicts_Get(SQL_Cursor, sql)
	if Rows is None:
		return None
	return {Row["discord_id"] for Row in Rows}

#SQL Query for recording that the given discord users have had their starting points assigned (stamps initial_points_assigned_at)
#Only stamps users not already stamped, so the original assignment time is kept
def Initial_Assigned_Set(SQL_Connection, SQL_Cursor, discord_ids):
	if not discord_ids:
		return 0
	sql = "UPDATE discord_members SET initial_points_assigned_at = CURRENT_TIMESTAMP WHERE discord_id = %s AND initial_points_assigned_at IS NULL"
	try:
		SQL_Cursor.executemany(sql, [(discord_id,) for discord_id in discord_ids])
		SQL_Connection.commit()
	except Exception:
		SQL_Connection.rollback()
		raise
	return SQL_Cursor.rowcount

#Earliest join_date per discord user across all of their linked, current OSRS accounts, optionally filtered by discord_id
#Overlapping accounts collapse to a single membership start, so no month is ever counted twice for one discord user
def Membership_Start_Get(SQL_Cursor, Exclude_Discord_Ids=None, Include_Discord_Ids=None):
	Rows = Linked_Current_Members_Get(SQL_Cursor)
	if Rows is None:
		return None
	Start_By_Discord_Id = {}
	for Row in Rows:
		discord_id = Row["discord_id"]
		if Exclude_Discord_Ids is not None and discord_id in Exclude_Discord_Ids:
			continue
		if Include_Discord_Ids is not None and discord_id not in Include_Discord_Ids:
			continue
		if discord_id not in Start_By_Discord_Id or Row["join_date"] < Start_By_Discord_Id[discord_id]:
			Start_By_Discord_Id[discord_id] = Row["join_date"]
	return Start_By_Discord_Id

#First instant of the month after the given month/year
def Month_End(Year, Month):
	if Month == 12:
		return datetime.datetime(Year + 1, 1, 1)
	return datetime.datetime(Year, Month + 1, 1)

#Every (year, month) from the earliest membership start up to and including the last completed month
def Completed_Months_Get(Start_By_Discord_Id, Now):
	if not Start_By_Discord_Id:
		return []
	Earliest = min(Start_By_Discord_Id.values())
	Year, Month = Earliest.year, Earliest.month
	Months = []
	while Month_End(Year, Month) <= datetime.datetime(Now.year, Now.month, 1):
		Months.append((Year, Month))
		Month += 1
		if Month > 12:
			Year, Month = Year + 1, 1
	return Months

#Discord users who were clan members in the given month/year (joined on or before the month's end and still a member)
def Month_Members_Get(Start_By_Discord_Id, Year, Month):
	End = Month_End(Year, Month)
	return [discord_id for discord_id, Start in Start_By_Discord_Id.items() if Start < End]

#SQL Query for the enabled membership token already covering the given month/year
def Membership_Token_Get(SQL_Cursor, Year, Month):
	sql = """SELECT pmt.token_id FROM points_membership_tokens AS pmt
		INNER JOIN points_tokens AS tok ON tok.token_id = pmt.token_id
		WHERE pmt.membership_year = %s AND pmt.membership_month = %s AND tok.token_enabled = TRUE
		ORDER BY pmt.token_id LIMIT 1"""
	SQL_Cursor.execute(sql, (Year, Month))
	row = SQL_Cursor.fetchone()
	if row is None:
		return None
	return row[0]

#Creates a source_id = 3 token for the given month/year and records which month it covers
def Membership_Token_Create(SQL_Connection, SQL_Cursor, author_discord_id, Year, Month):
	Token_ID = sql_points.Token_Create(SQL_Connection, SQL_Cursor, MEMBERSHIP_POINTS_SOURCE_ID, author_discord_id, False)
	sql = "INSERT INTO points_membership_tokens (token_id, membership_year, membership_month) VALUES (%s, %s, %s)"
	try:
		SQL_Cursor.execute(sql, (Token_ID, Year, Month))
		SQL_Connection.commit()
	except Exception:
		SQL_Connection.rollback()
		#An unmapped token can't be found again, so disable it rather than leave it orphaned
		sql_points.Token_Toggle_Enable(SQL_Connection, SQL_Cursor, author_discord_id, Token_ID, False)
		raise
	return Token_ID

#SQL Query for the discord users who already have a transaction under the given token
def Token_Members_Get(SQL_Cursor, Token_ID):
	sql = "SELECT DISTINCT discord_id FROM points_transactions WHERE token_id = %s"
	Rows = sql_config.Query_Dicts_Get(SQL_Cursor, sql, (Token_ID,))
	if Rows is None:
		raise RuntimeError("Token_Members_Get query failed for token %s" % Token_ID)
	return {Row["discord_id"] for Row in Rows}

#Assigns one month's membership points to the given discord users, adding them to that month's token (created if it doesn't exist yet)
#Users already in that month's token are skipped. Returns (token_id, list of discord_ids added)
def Membership_Points_Assign_Month(SQL_Connection, SQL_Cursor, author_discord_id, Discord_Ids, Year, Month, Points):
	Token_ID = Membership_Token_Get(SQL_Cursor, Year, Month)
	if Token_ID is None:
		Token_ID = Membership_Token_Create(SQL_Connection, SQL_Cursor, author_discord_id, Year, Month)
		Already_Assigned = set()
	else:
		Already_Assigned = Token_Members_Get(SQL_Cursor, Token_ID)
	Members = [discord_id for discord_id in Discord_Ids if discord_id not in Already_Assigned]
	if Members:
		sql_points.Transaction_Create(SQL_Connection, SQL_Cursor, Token_ID, [discord.Object(id=discord_id) for discord_id in Members], Points)
		print("INIT : Token ID %s assigned %04d-%02d membership points to %s discord users" % (Token_ID, Year, Month, len(Members)))
	return Token_ID, Members

#SQL Query for removing specific (token_id, discord_id) transactions - used to undo a partially-applied run
def Transactions_Remove(SQL_Connection, SQL_Cursor, Pairs):
	if not Pairs:
		return 0
	sql = "DELETE FROM points_transactions WHERE token_id = %s AND discord_id = %s"
	try:
		SQL_Cursor.executemany(sql, Pairs)
		SQL_Connection.commit()
	except Exception as Error:
		SQL_Connection.rollback()
		print("SQL : Transactions_Remove failed : %r" % Error)
		return None
	return SQL_Cursor.rowcount

#SQL Query for the given discord members' current promotion rank and the points that rank requires
def Member_Ranks_Get(SQL_Cursor, discord_ids):
	Placeholders = ", ".join(["%s"] * len(discord_ids))
	sql = """SELECT m.discord_id, m.promotion_rank_id, COALESCE(dpr.points_required, 0) AS points_required
		FROM discord_members AS m
		INNER JOIN discord_promotion_ranks AS dpr ON dpr.promotion_rank_id = m.promotion_rank_id
		WHERE m.discord_id IN (%s)""" % Placeholders
	return sql_config.Query_Dicts_Get(SQL_Cursor, sql, tuple(discord_ids))

#Tops each given discord user up to their current rank's points_required, one source_id = 1 token per user
#Users already at or above their rank's requirement are left alone. Token ids are appended to Created_Token_IDs as they're made
def Rank_Points_Top_Up(SQL_Connection, SQL_Cursor, author_discord_id, discord_ids, Created_Token_IDs):
	Rows = Member_Ranks_Get(SQL_Cursor, discord_ids)
	if Rows is None:
		raise RuntimeError("Member_Ranks_Get query failed")
	for Row in Rows:
		Totals = sql_points.User_Total_Get(SQL_Connection, SQL_Cursor, Row["discord_id"])
		if Totals is None:
			continue
		Difference = Row["points_required"] - Totals["total"]
		if Difference <= 0:
			continue
		Token_ID = sql_points.Token_Create(SQL_Connection, SQL_Cursor, RANK_TOP_UP_POINTS_SOURCE_ID, author_discord_id, False)
		Created_Token_IDs.append(Token_ID)
		sql_points.Transaction_Create(SQL_Connection, SQL_Cursor, Token_ID, discord.Object(id=Row["discord_id"]), Difference)
		print("INIT : Token ID %s topped up discord_id %s by %s points to promotion_rank_id %s" % (Token_ID, Row["discord_id"], Difference, Row["promotion_rank_id"]))
	return Created_Token_IDs

#Adds every user in Start_By_Discord_Id to each completed month's membership token they were a member for and aren't already in
#Inserted (token_id, discord_id) pairs and touched token ids are appended to the passed lists as they're made, so callers can undo on failure
def Membership_Months_Assign(SQL_Connection, SQL_Cursor, author_discord_id, Start_By_Discord_Id, Points, Now, Inserted_Pairs, Membership_Token_IDs):
	for Year, Month in Completed_Months_Get(Start_By_Discord_Id, Now):
		Members = Month_Members_Get(Start_By_Discord_Id, Year, Month)
		if not Members:
			continue
		Token_ID, Added = Membership_Points_Assign_Month(SQL_Connection, SQL_Cursor, author_discord_id, Members, Year, Month, Points)
		Inserted_Pairs.extend((Token_ID, discord_id) for discord_id in Added)
		if Added:
			Membership_Token_IDs.append(Token_ID)

#Scheduled check: gives every linked current member who has already had starting points any completed month they're missing
#(normally just the month that ended on the 1st, but also catches up on any month skipped while the bot was down)
#Returns a summary dict on success, or a result code: "no_points_value", None (error)
def Membership_Points_Assign_Missed(SQL_Connection, SQL_Cursor, author_discord_id):
	Already_Assigned = Initial_Assigned_Get(SQL_Cursor)
	if Already_Assigned is None:
		return None
	#Users without starting points yet are left to Initial_Points_Assignment, which also handles their rank top-up
	Start_By_Discord_Id = Membership_Start_Get(SQL_Cursor, Include_Discord_Ids=Already_Assigned)
	if Start_By_Discord_Id is None:
		return None
	if not Start_By_Discord_Id:
		return {"discord_ids": [], "membership_token_ids": []}
	Points = sql_points.Value_Get(SQL_Cursor, MEMBERSHIP_POINTS_SOURCE_ID, MEMBERSHIP_POINTS_CONTRIBUTION_LEVEL)
	if not Points:
		print("MEMBERSHIP : No membership points value found for source_id %s, contribution_level %s" % (MEMBERSHIP_POINTS_SOURCE_ID, MEMBERSHIP_POINTS_CONTRIBUTION_LEVEL))
		return "no_points_value"

	Now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
	Inserted_Pairs = []
	Membership_Token_IDs = []
	try:
		Membership_Months_Assign(SQL_Connection, SQL_Cursor, author_discord_id, Start_By_Discord_Id, Points, Now, Inserted_Pairs, Membership_Token_IDs)
	except Exception as Error:
		SQL_Connection.rollback()
		print("MEMBERSHIP : Missed month assignment failed : %r" % Error)
		Transactions_Remove(SQL_Connection, SQL_Cursor, Inserted_Pairs)
		return None

	Discord_Ids = sorted({discord_id for Token_ID, discord_id in Inserted_Pairs})
	print("MEMBERSHIP : %s membership transactions added for %s discord users across %s months" % (len(Inserted_Pairs), len(Discord_Ids), len(Membership_Token_IDs)))
	return {
		"discord_ids": Discord_Ids,
		"membership_token_ids": Membership_Token_IDs
	}

#Assigns starting points to every linked discord user who hasn't had them yet: monthly membership points for every
#completed month, then a top-up to their current rank. Safe to run on every startup - users are only ever processed once
#Returns a summary dict on success, or a result code: "no_links", "no_points_value", None (error)
def Initial_Points_Assignment(SQL_Connection, SQL_Cursor, author_discord_id):
	Already_Assigned = Initial_Assigned_Get(SQL_Cursor)
	if Already_Assigned is None:
		return None
	Start_By_Discord_Id = Membership_Start_Get(SQL_Cursor, Already_Assigned)
	if Start_By_Discord_Id is None:
		return None
	if not Start_By_Discord_Id:
		if not Already_Assigned:
			print("INIT : No linked current OSRS members found")
			return "no_links"
		print("INIT : No discord users awaiting starting points")
		return {"discord_ids": [], "membership_token_ids": [], "rank_token_ids": []}
	Points = sql_points.Value_Get(SQL_Cursor, MEMBERSHIP_POINTS_SOURCE_ID, MEMBERSHIP_POINTS_CONTRIBUTION_LEVEL)
	if not Points:
		print("INIT : No membership points value found for source_id %s, contribution_level %s" % (MEMBERSHIP_POINTS_SOURCE_ID, MEMBERSHIP_POINTS_CONTRIBUTION_LEVEL))
		return "no_points_value"

	print("INIT : Assigning starting points to %s discord users" % len(Start_By_Discord_Id))
	#MySQL DATETIMEs come back naive, so compare against a naive UTC "now"
	Now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
	Discord_Ids = list(Start_By_Discord_Id.keys())
	Inserted_Pairs = []
	Membership_Token_IDs = []
	Rank_Token_IDs = []
	try:
		Membership_Months_Assign(SQL_Connection, SQL_Cursor, author_discord_id, Start_By_Discord_Id, Points, Now, Inserted_Pairs, Membership_Token_IDs)
		Rank_Points_Top_Up(SQL_Connection, SQL_Cursor, author_discord_id, Discord_Ids, Rank_Token_IDs)
		Initial_Assigned_Set(SQL_Connection, SQL_Cursor, Discord_Ids)
	except Exception as Error:
		SQL_Connection.rollback()
		print("INIT : Starting points assignment failed : %r" % Error)
		#Undo this run so the next startup retries these users without double-counting.
		#Month tokens are shared with other users, so only this run's transactions are removed from them
		Transactions_Remove(SQL_Connection, SQL_Cursor, Inserted_Pairs)
		for Token_ID in Rank_Token_IDs:
			sql_points.Token_Toggle_Enable(SQL_Connection, SQL_Cursor, author_discord_id, Token_ID, False)
		return None

	print("INIT : Starting points assigned - %s discord users, %s membership tokens, %s rank top-up tokens" % (len(Discord_Ids), len(Membership_Token_IDs), len(Rank_Token_IDs)))
	return {
		"discord_ids": Discord_Ids,
		"membership_token_ids": Membership_Token_IDs,
		"rank_token_ids": Rank_Token_IDs
	}

#Runs on every startup: assigns starting points to any linked discord user who hasn't had them yet,
#and marks bot_config.initial_configuration_complete once the first run succeeds
def Initial_Configuration_Run(SQL_Connection, SQL_Cursor, author_discord_id):
	Complete = Config_Get(SQL_Cursor, INITIAL_CONFIGURATION_CONFIG_NAME)
	if Complete is None:
		print("INIT : bot_config '%s' not found" % INITIAL_CONFIGURATION_CONFIG_NAME)
		return None
	if not Complete:
		print("INIT : Initial configuration not complete - running initial points assignment")
	else:
		print("INIT : Checking for discord users missing starting points")

	Result = Initial_Points_Assignment(SQL_Connection, SQL_Cursor, author_discord_id)
	if not isinstance(Result, dict):
		print("INIT : Starting points assignment did not complete (%s) - will retry on next startup" % Result)
	elif not Complete:
		Config_Set(SQL_Connection, SQL_Cursor, INITIAL_CONFIGURATION_CONFIG_NAME, 1)
	return Result
