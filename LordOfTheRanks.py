# Import core libraries
import os
import importlib
import dotenv
import json
import discord
import mysql.connector
# Load all LordOfTheRanks functions
from Functions import *

## Set required discord bot environment flags
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents = intents)
tree = discord.app_commands.CommandTree(client)

#Load environment variables from external file
dotenv.load_dotenv()
#Bot's private token to connect to the discord API
DISCORD_TOKEN = str(os.getenv("DISCORD_API_TOKEN"))
DISCORD_USER = str(os.getenv("DISCORD_USER"))
#Homeland's server UUID; ensures nobody else can use the bot to avoid conflicts if other servers get access to it for whatever reason (as we're not making a universal product)
DISCORD_GUILD = str(os.getenv("DISCORD_GUILD"))
#SQL Database connection environment variables
SQL_HOST = str(os.getenv("MYSQL_HOST"))
SQL_USER = str(os.getenv("MYSQL_USER"))
SQL_PASS = str(os.getenv("MYSQL_PASS"))
#WOM connection environment variables
WOM_USER = str(os.getenv("WOM_USER"))
WOM_TOKEN = str(os.getenv("WOM_API_TOKEN"))
WOM_GUILD = str(os.getenv("WOM_GUILD"))

#SQL Database name
SQL_Database = 'lordoftheranks'
#SQL Database definition
SQL_Table_Definitions_Filepath = "MySQL_Table_Definitions.json"
SQL_Table_Default_Data_Filepath = "MySQL_Table_Default_Data.json"

#Connect to the SQL database and verify the database contents and structure are as expected
SQL_Connection, SQL_Cursor = sql_config.SQL_Verify_And_Connect(SQL_HOST, SQL_USER, SQL_PASS, SQL_Database, SQL_Table_Definitions_Filepath, SQL_Table_Default_Data_Filepath)

# Namespace variables required to execute discord command code
Command_Namespace = {
	"tree": tree,
	"discord": discord,
	"app_commands": discord.app_commands,
	"DISCORD_GUILD": DISCORD_GUILD,
	"DISCORD_USER": DISCORD_USER,
	"SQL_Connection": SQL_Connection,
	"SQL_Cursor": SQL_Cursor
}

#Execute all slash-command code as submodules to keep body code easy to read
Directory = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Commands")
Directory_Contents = os.scandir(Directory)
print("Looking for Slash-Command files located in '% s':" % Directory)
for Command_File in Directory_Contents:
	if Command_File.is_file() and Command_File.name.endswith(".py"):
		print("Executing module: " + Command_File.name)
		with open(Command_File.path, "r", encoding="utf-8") as f:
			Command_Module_Code = f.read()
		exec(Command_Module_Code, Command_Namespace)

# Display ready message
@client.event
async def on_ready():
	print('We have logged in as {0.user}'.format(client))

	#Push command tree to users (not homeland for now)
	print("Syncing Command Tree")
	existing = tree.get_commands(guild=discord.Object(id=DISCORD_GUILD))
	print(f"Locally registered before sync: {[c.name for c in existing]}")
	try:
		synced = await tree.sync(guild=discord.Object(id=DISCORD_GUILD))
		print(f"Synced {len(synced)} command(s): {[c.name for c in synced]}")
	except Exception as e:
		print(f"Sync failed: {e}")
	#Get guild roles
	#print("Getting Guild Roles")
	#Guild_Role_List = await discord_data.Roles_Get(client, guild_id=DISCORD_GUILD)
	#discord_data.Roles_Display(Guild_Role_List)

	#Get guild members
	#print("Getting Guild Members")
	#Guild_Member_List = discord_data.Members_Get(client, guild_id=DISCORD_GUILD);
	#discord_data.Members_Display(Guild_Member_List)

	#Update guild members in the MySQL Database
	#sql_update.Discord_Member_Update(SQL_Connection, Guild_Member_List)
	
	#Bot ready to perform async actions on demand
	print("Bot Ready!")

# Connect to discord using the bot's API Token
print("Connecting bot to discord")
client.run(DISCORD_TOKEN)