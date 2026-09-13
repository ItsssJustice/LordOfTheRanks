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