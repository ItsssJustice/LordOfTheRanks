#SQL Query for getting the points sources list
def Points_Sources_Get(SQL_Cursor):
	sql = "SELECT source_id, source_description FROM points_sources ORDER BY source_id"
	SQL_Cursor.execute(sql)
	rows = SQL_Cursor.fetchall()
	Points_Sources = {}
	for row in rows:
		source_id, source_description = row
		Points_Sources[source_id] = {
			"source_id": source_id,
			"source_description": source_description
		}
	print(f"SQL : Retriving points values for standard categories")
	return list(Points_Sources.values())

#SQL Query for creating a points token and the associated points for users
def Points_Token_Create(SQL_Connection, SQL_Cursor, source_id, author_discord_id, manual_assignment):
	sql = "INSERT INTO points_tokens (source_id, created_by_discord_id, manual_assignment) VALUES (%s, %s, %s)"
	SQL_Cursor.execute(sql, (source_id, author_discord_id, manual_assignment))
	SQL_Connection.commit()
	Token_ID = SQL_Cursor.lastrowid
	print(f"SQL : Created TOKEN ID : {Token_ID}")
	return Token_ID

#SQL Query for inserting points transactions - accepts a single member or a list of members
def Points_Transaction_Insert(SQL_Connection, SQL_Cursor, token_id, member, points):
	# Normalize to a list so single-member and multi-member calls share the same code path
	members = member if isinstance(member, list) else [member]
	sql = "INSERT INTO points_transactions (token_id, discord_id, points) VALUES (%s, %s, %s)"
	params = [(token_id, member.id, points) for member in members]
	SQL_Cursor.executemany(sql, params)
	SQL_Connection.commit()
	Transactions = SQL_Cursor.rowcount
	print(f"SQL : Token ID {token_id} created {Transactions} transactions")
	return SQL_Cursor.rowcount

#SQL Query for enabling or disabling a points token
def Points_Token_Enabled_Toggle(SQL_Connection, SQL_Cursor, author_discord_id, token_id, enabled):
	# Also ensure created_at is within the allowed number of days
	sql = "SELECT config_executed FROM bot_config WHERE config_name=%s"
	SQL_Cursor.execute(sql, ("token_id_read_only_days",))
	row = SQL_Cursor.fetchone()
	if row is None:
		return None
	token_id_read_only_days = row[0]
	# Check the token exists first, and grab its current enabled state
	sql = "SELECT token_enabled FROM points_tokens WHERE token_id = %s AND created_at >= NOW() - INTERVAL %s DAY"
	SQL_Cursor.execute(sql, (token_id, token_id_read_only_days))
	row = SQL_Cursor.fetchone()
	if row is None:
		return None
	# Skip the update if the value wouldn't actually change
	if row[0] == enabled:
		return False
	# Update the enabled flag and record who changed it
	sql = "UPDATE points_tokens SET token_enabled = %s, token_disabled_by_discord_id = %s WHERE token_id = %s"
	SQL_Cursor.execute(sql, (enabled, author_discord_id, token_id))
	SQL_Connection.commit()
	print(f"SQL : Token ID {token_id} : changed to {enabled}")
	return True

#SQL Query for obtaining the points value for a given token
def Points_Get_Value(SQL_Cursor, source_id, level_id, addition, other_points: int = 0):
	#Use custom points value, or standard tables
	if(source_id == 2):
		Value = other_points
	else:
		sql = "SELECT points FROM points_values WHERE source_id=%s AND contribution_level=%s"
		SQL_Cursor.execute(sql, (source_id, level_id))
		row = SQL_Cursor.fetchone()
		if row is None:
			return None
		else:
			Value = row[0]
	#Ensure that negative values are handled
	Value = abs(Value)
	if addition == 0:
		Value = -Value
	return Value