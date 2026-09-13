from Functions import sql_config

#Get a single bot_timings row by id, as a dict, or None if not found
def Timing_Get(SQL_Cursor, Timing_Id):
	Query = "SELECT timing_id, name, interval_seconds, offset_seconds, run_on_startup, update_time FROM bot_timings WHERE timing_id = %s"
	Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Timing_Id,))
	if not Rows:
		return None
	return Rows[0]

#Get every bot_timings row except the named one (the scheduler loop's own entry, which
#Scheduled_Task_Loop reads directly rather than being dispatched to by Scheduled_Tasks)
def Timings_Get_All_Except(SQL_Cursor, Exclude_Name):
	Query = "SELECT timing_id, name, interval_seconds, offset_seconds, run_on_startup, update_time FROM bot_timings WHERE name != %s"
	return sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Exclude_Name,))

#Get every bot_timings row flagged to run once at startup, regardless of its own grid timing
def Timings_Get_Run_On_Startup(SQL_Cursor):
	Query = "SELECT timing_id, name, interval_seconds, offset_seconds, run_on_startup, update_time FROM bot_timings WHERE run_on_startup = TRUE"
	return sql_config.Query_Dicts_Get(SQL_Cursor, Query)

#Stamp a timing entry's update_time as now, marking its block as having just run
def Timing_Update_Time(SQL_Connection, SQL_Cursor, Timing_Id):
	Query = "UPDATE bot_timings SET update_time = CURRENT_TIMESTAMP WHERE timing_id = %s"
	try:
		SQL_Cursor.execute(Query, (Timing_Id,))
		SQL_Connection.commit()
	except Exception:
		SQL_Connection.rollback()
		raise
	print(f"SQL : Timing ID {Timing_Id} : update_time refreshed")