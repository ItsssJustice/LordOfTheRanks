import datetime

#Verify a competition exists and return all of its fields as a tuple, or None if not found
def WOM_Competition_Get(SQL_Connection, SQL_Cursor, Competition_id):
	sql = "SELECT competition_id, title, starts_at, ends_at, metric, points_assigned, created_at, updated_at FROM competitions WHERE competition_id = %s"
	SQL_Cursor.execute(sql, (Competition_id,))
	row = SQL_Cursor.fetchone()
	if row is None:
		return None
	return row

#Insert a new competition record, refusing if one already exists for this id
def WOM_Competition_Create(SQL_Connection, SQL_Cursor, Competition_id, title, starts_at, ends_at, created_at, metric):
	Existing = WOM_Competition_Get(SQL_Connection, SQL_Cursor, Competition_id)
	if Existing is not None:
		print(f"SQL : Competition ID {Competition_id} already exists, skipping create")
		return None
	sql = "INSERT INTO competitions (competition_id, title, starts_at, ends_at, metric, created_at) VALUES (%s, %s, %s, %s, %s, %s)"
	try:
		SQL_Cursor.execute(sql, (Competition_id, title, starts_at, ends_at, metric, created_at))
		SQL_Connection.commit()
	except Exception:
		SQL_Connection.rollback()
		raise
	print(f"SQL : Created Competition ID : {Competition_id}")
	return Competition_id

#Mark a competition's points as assigned, stamping updated_at with the current time
def WOM_Competition_Points_Assigned(SQL_Connection, SQL_Cursor, Competition_id):
	sql = "UPDATE competitions SET points_assigned = TRUE, updated_at = CURRENT_TIMESTAMP WHERE competition_id = %s"
	try:
		SQL_Cursor.execute(sql, (Competition_id,))
		if SQL_Cursor.rowcount == 0:
			SQL_Connection.rollback()
			return None
		SQL_Connection.commit()
	except Exception:
		SQL_Connection.rollback()
		raise
	print(f"SQL : Competition ID {Competition_id} : points_assigned set to TRUE")
	return True

#Whether points have already been assigned for a competition. False if it isn't recorded yet
def WOM_Competition_Points_Assigned_Get(SQL_Cursor, Competition_id):
	SQL_Cursor.execute("SELECT points_assigned FROM competitions WHERE competition_id = %s", (Competition_id,))
	row = SQL_Cursor.fetchone()
	if row is None:
		return False
	return bool(row[0])

#WOM hands back ISO-8601 strings with an offset; store them as naive UTC like the rest of the bot
def _WOM_Datetime(Value):
	Parsed = datetime.datetime.fromisoformat(Value)
	if Parsed.tzinfo is not None:
		Parsed = Parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
	return Parsed

#Insert or update a competition from wom_data.Competition_Get's validated "competition" dict.
#Title, dates and metric follow WOM; points_assigned is left untouched on an existing row.
def WOM_Competition_Upsert_From_Data(SQL_Connection, SQL_Cursor, Competition):
	sql = """INSERT INTO competitions (competition_id, title, starts_at, ends_at, metric, created_at) VALUES (%s, %s, %s, %s, %s, %s)
		ON DUPLICATE KEY UPDATE title = VALUES(title), starts_at = VALUES(starts_at), ends_at = VALUES(ends_at), metric = VALUES(metric)"""
	try:
		SQL_Cursor.execute(sql, (Competition["competition_id"], Competition["title"][:255],
			_WOM_Datetime(Competition["starts_at"]), _WOM_Datetime(Competition["ends_at"]),
			Competition["metric"][:100], datetime.datetime.utcnow()))
		SQL_Connection.commit()
	except Exception:
		SQL_Connection.rollback()
		raise
	print(f"SQL : Competition ID {Competition['competition_id']} : recorded")
	return Competition["competition_id"]
