#Initial configuration of the MySQL database
#Verify the database structure and connect to the MySQL database
def SQL_Verify_And_Connect(SQL_Host, SQL_User, SQL_Pass, SQL_Database, SQL_Table_Definitions_Filepath, SQL_Table_Default_Data_Filepath):
	#Connect to the MySQL server
	import mysql.connector
	SQL_Connection = mysql.connector.connect(
	  host = SQL_Host,
	  user = SQL_User,
	  password = SQL_Pass
	)
	#Display mysql connection
	print(f"SQL : Connecting to MySQL Database : {SQL_Connection}")

	#Create cursor to move around the database to gather requests
	SQL_Cursor = SQL_Connection.cursor()
	#Verify the MySQL Database exists
	Database_Verify(SQL_Cursor, SQL_Database);
	print(f"SQL : Reconnecting to MySQL Database After Locating Database")
	#disconnect from the MySQL database
	SQL_Connection.disconnect()
	#re-connect to the MySQL server with the specific database included (to simplify later requests)
	SQL_Connection = mysql.connector.connect(
	  host = SQL_Host,
	  user = SQL_User,
	  password = SQL_Pass,
	  database = SQL_Database
	)
	#Display mysql connection
	print(f" SQL : Connecting to MySQL Database : {SQL_Connection}")
	#Wrap the connection so it reconnects by itself after an idle timeout or server restart -
	#see Reconnecting_Connection below. Everything else keeps using it exactly as before.
	SQL_Connection = Reconnecting_Connection(SQL_Connection)
	#Create cursor to move around the database to gather requests
	SQL_Cursor = SQL_Connection.cursor(buffered=True)
	#Verify all tables exist
	try:
	    Table_Verify(SQL_Cursor, SQL_Table_Definitions_Filepath)
	    if SQL_Table_Default_Data_Filepath:
	        Table_Default_Data_Verify(SQL_Cursor, SQL_Table_Default_Data_Filepath)
	    SQL_Connection.commit()
	    print("SQL : Schema sync complete.")
	except mysql.connector.Error as err:
	    SQL_Connection.rollback()
	    print(f"SQL : Error during schema sync: {err}")
	#finally:
	    #SQL_Cursor.close()
	    #SQL_Connection.close()
	return SQL_Connection, SQL_Cursor

# ---------------------------------------------------------------------------
# Reconnecting to the database
# ---------------------------------------------------------------------------
#
# The bot holds one MySQL connection for its whole life. MySQL closes a connection
# that has been idle for wait_timeout (8 hours by default), and a server restart
# drops it too; before this, every query after that failed, and Query_Dicts_Get
# swallowing the error meant they quietly returned None.
#
# Reconnecting_Connection / Reconnecting_Cursor wrap the real connection and its
# cursors, and pass everything else straight through, so the SQL_Connection and
# SQL_Cursor handed around the bot are used exactly as before:
#   - Before running a statement after SQL_IDLE_PING_SECONDS without using the
#     connection, it pings it, reconnecting if the server has dropped it. This is
#     what catches the idle timeout. A busy connection isn't pinged, so the
#     statements of one transaction never have a reconnect land between them.
#   - If a statement still fails because the connection was lost (e.g. the server
#     restarted mid-idle-window), it reconnects straight away. A SELECT/SHOW is
#     then retried once, since reading twice is harmless. Anything else re-raises
#     as before, so the caller's own rollback/error handling runs and nothing is
#     half-replayed; the next statement goes to the fresh connection.
#   - Reconnecting waits up to SQL_RECONNECT_ATTEMPTS x SQL_RECONNECT_DELAY seconds.
#     If the server is still unreachable it raises, and the next statement tries again.

import time
import mysql.connector

SQL_IDLE_PING_SECONDS = 60
SQL_RECONNECT_ATTEMPTS = 3
SQL_RECONNECT_DELAY = 2

class Reconnecting_Connection:
	def __init__(self, Connection):
		self._Connection = Connection
		self._Last_Used = time.monotonic()

	def Touch(self):
		self._Last_Used = time.monotonic()

	def Ensure_Connected(self):
		"""Ping (reconnecting if needed) when the connection has sat idle."""
		if time.monotonic() - self._Last_Used >= SQL_IDLE_PING_SECONDS:
			self._Connection.ping(reconnect=True, attempts=SQL_RECONNECT_ATTEMPTS, delay=SQL_RECONNECT_DELAY)
			self.Touch()

	def Reconnect(self):
		print("SQL : Connection lost - reconnecting")
		self._Connection.reconnect(attempts=SQL_RECONNECT_ATTEMPTS, delay=SQL_RECONNECT_DELAY)
		self.Touch()
		print("SQL : Reconnected")

	def Is_Lost(self):
		try:
			return not self._Connection.is_connected()
		except Exception:
			return True

	def cursor(self, *Args, **Kwargs):
		self.Ensure_Connected()
		return Reconnecting_Cursor(self, Args, Kwargs)

	def commit(self):
		self._Connection.commit()
		self.Touch()

	def rollback(self):
		try:
			self._Connection.rollback()
		except mysql.connector.Error:
			#A rollback on a lost connection has nothing to undo - the server already did it
			if not self.Is_Lost():
				raise
		self.Touch()

	#Everything else (in_transaction, disconnect, ...) is the real connection's
	def __getattr__(self, Name):
		return getattr(self._Connection, Name)

	def __repr__(self):
		return repr(self._Connection)

class Reconnecting_Cursor:
	def __init__(self, Owner, Args, Kwargs):
		self._Owner = Owner
		self._Args = Args
		self._Kwargs = Kwargs
		self._Cursor = Owner._Connection.cursor(*Args, **Kwargs)

	def _Run(self, Method, Query, *Args, **Kwargs):
		self._Owner.Ensure_Connected()
		try:
			Result = getattr(self._Cursor, Method)(Query, *Args, **Kwargs)
		except mysql.connector.Error:
			if not self._Owner.Is_Lost():
				raise
			self._Owner.Reconnect()
			self._Cursor = self._Owner._Connection.cursor(*self._Args, **self._Kwargs)
			if not str(Query).lstrip().upper().startswith(("SELECT", "SHOW")):
				raise
			Result = getattr(self._Cursor, Method)(Query, *Args, **Kwargs)
		self._Owner.Touch()
		return Result

	def execute(self, Query, *Args, **Kwargs):
		return self._Run("execute", Query, *Args, **Kwargs)

	def executemany(self, Query, *Args, **Kwargs):
		return self._Run("executemany", Query, *Args, **Kwargs)

	#Everything else (fetchone, fetchall, rowcount, column_names, lastrowid, close, ...) is the real cursor's
	def __getattr__(self, Name):
		return getattr(self._Cursor, Name)

	def __iter__(self):
		return iter(self._Cursor)

#Ensure the database exists
def Database_Verify(SQL_Cursor, SQL_Database):
	print("SQL : Verifying Database Exists")
	#Gather all databases on the MySQL server
	Database_List = Database_Get_List(SQL_Cursor)

	#Create the database if no database exists
	Database_Found = True if any(Database == SQL_Database for Database in Database_List) else False
	if not Database_Found:
		print("SQL : Database Not Found")
		SQL_Cursor.execute("CREATE DATABASE " + SQL_Database)
		print("SQL : Creating Database")
	else:
		print("SQL : Database Found")

#Get a list of all databases on the MySQL server
def Database_Get_List(SQL_Cursor):
	print("SQL : Retriving Database List")
	SQL_Cursor.execute("SHOW DATABASES")
	return{Database[0] for Database in SQL_Cursor.fetchall()}

#Verify all tables in the selected database exists
def Table_Verify(SQL_Cursor, Table_Definitions_Filepath):
	Table_Definitions = Database_Table_JSON_Read(Table_Definitions_Filepath)
	existing_tables = Table_Get_List(SQL_Cursor)
	for table_name, columns in Table_Definitions.items():
		print(f"SQL : Verifying Table `{table_name}` Exists")
		if table_name not in existing_tables:
			Table_Create(SQL_Cursor, table_name, columns)
		else:
			print(f"SQL : Table `{table_name}` Found — Checking Columns")
			existing_columns = Table_Column_Get(SQL_Cursor, table_name)
			missing = [c for c in columns if c not in existing_columns]
			if missing:
				print(f"SQL : Table `{table_name}` - Adding Columns")
				Table_Column_Add(SQL_Cursor, table_name, columns, existing_columns)
			else:
				print(f"SQL : Table `{table_name}` - All Columns Present")

#Get a list of all tables in the MySQL database
def Table_Get_List(SQL_Cursor):
	print("SQL : Retriving Table List")
	SQL_Cursor.execute("SHOW TABLES")
	return {row[0] for row in SQL_Cursor.fetchall()}

#Create a table in the MySQL database
def Table_Create(SQL_Cursor, table_name, columns):
	column_defs = ", ".join(f"`{col}` {definition}" for col, definition in columns.items())
	sql = f"CREATE TABLE `{table_name}` ({column_defs})"
	print(f"SQL : Creating Table `{table_name}`")
	SQL_Cursor.execute(sql)

#Get a list of columns that exist in a given MySQL database table
def Table_Column_Get(SQL_Cursor, table_name):
	SQL_Cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
	return {row[0] for row in SQL_Cursor.fetchall()}

#Add a column to a given MySQL database table
def Table_Column_Add(SQL_Cursor, table_name, columns, existing_columns):
	for col, definition in columns.items():
		if col not in existing_columns:
			sql = f"ALTER TABLE `{table_name}` ADD COLUMN `{col}` {definition}"
			print(f"SQL : Adding missing column `{col}` to `{table_name}`...")
			SQL_Cursor.execute(sql)

#Verify all default data rows exist in their tables, inserting any that are missing
def Table_Default_Data_Verify(SQL_Cursor, Default_Data_Filepath):
	Default_Data = Database_Table_JSON_Read(Default_Data_Filepath)
	for table_name, table_data in Default_Data.items():
		Key_Column = table_data["key"]
		Rows = table_data["rows"]
		print(f"SQL : Verifying Default Data For Table `{table_name}`")
		for row in Rows:
			if Table_Default_Data_Row_Exists(SQL_Cursor, table_name, Key_Column, row):
				print(f"SQL : Default Row `{row.get(Key_Column)}` Found In `{table_name}`")
			else:
				print(f"SQL : Default Row `{row.get(Key_Column)}` Missing In `{table_name}` — Inserting")
				Table_Default_Data_Row_Insert(SQL_Cursor, table_name, row)

#Check whether a default data row already exists, matched by the table's key column
def Table_Default_Data_Row_Exists(SQL_Cursor, table_name, Key_Column, row):
	sql = f"SELECT 1 FROM `{table_name}` WHERE `{Key_Column}` = %s LIMIT 1"
	SQL_Cursor.execute(sql, (row[Key_Column],))
	return SQL_Cursor.fetchone() is not None

#Insert a single default data row into the given table
def Table_Default_Data_Row_Insert(SQL_Cursor, table_name, row):
	columns = ", ".join(f"`{col}`" for col in row.keys())
	placeholders = ", ".join(["%s"] * len(row))
	sql = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"
	SQL_Cursor.execute(sql, tuple(row.values()))

#Load table definitions from JSON schema
def Database_Table_JSON_Read(Table_Definitions_Filepath):
	import json
	try:
		with open(Table_Definitions_Filepath, "r") as File:
			return json.load(File)
	except FileNotFoundError:
		raise SystemExit(f"SQL : Could not find table definitions file: {Table_Definitions_Filepath}")
	except json.JSONDecodeError as e:
		raise SystemExit(f"SQL : Invalid JSON in {Table_Definitions_Filepath}: {e}")

def Query_Dicts_Get(SQL_Cursor, Query: str, Params: tuple = None) -> list[dict]:
	try:
		print(f"SQL : Executing Query : {Query}")
		SQL_Cursor.execute(Query, Params)
		columns = SQL_Cursor.column_names
		rows = SQL_Cursor.fetchall()
		return [dict(zip(columns, row)) for row in rows]
	except Exception as err:
		print(f"SQL : Query failed : {err}")
		return None