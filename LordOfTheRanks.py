
# Import core libraries
import os
import asyncio
import datetime
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
ENV_TOKEN = str(os.getenv("DISCORD_BOT_API_TOKEN"))
#Homeland's server UUID; ensures nobody else can use the bot to avoid conflicts if other servers get access to it for whatever reason (as we're not making a universal product)
ENV_GUILD = str(os.getenv("DISCORD_GUILD"))
#SQL Database connection environment variables
SQL_Host = str(os.getenv("MYSQL_HOST"))
SQL_User = str(os.getenv("MYSQL_USER"))
SQL_Pass = str(os.getenv("MYSQL_PASS"))

#SQL Database name
SQL_Database = 'lordoftheranks'
#SQL Database definition
SQL_Table_Definitions_Filepath = "MySQL_Table_Definitions.json"

#Connect to the SQL database and verify the database contents and structure are as expected
SQL_Connection, SQL_Cursor = sql_config.SQL_Verify_And_Connect(SQL_Host, SQL_User, SQL_Pass, SQL_Database, SQL_Table_Definitions_Filepath)

# Namespace variables required to execute discord command code
Command_Namespace = {
    "client": client,
    "tree": tree,
    "discord": discord,
    "app_commands": discord.app_commands,
    "datetime": datetime,
    "ENV_GUILD": ENV_GUILD,
    #Poll support
    "poll_store": poll_store,
    "poll_format": poll_format,
    "poll_data": poll_data,
    "secret_store": secret_store,
    "secret_view": secret_view
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

# Publish the result of any secret ballot whose time is up. Native polls do not
# need this; discord expires those itself.
async def Close_Expired_Ballots():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            for Ballot_Record in list(secret_store.Get().values()):
                if Ballot_Record.get("closed") or not secret_store.Is_Closed(Ballot_Record):
                    continue
                print("Secret ballot '% s' reached its deadline, closing" % Ballot_Record["label"])
                await secret_view.Refresh_Message(client, secret_store.Close(Ballot_Record["label"]))
        except Exception as Error:
            print("Ballot closer hit an error: % r" % Error)
        await asyncio.sleep(60)

# Display ready message
@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

    #Push command tree to users (not homeland for now)
    print("Syncing Command Tree")
    await tree.sync(guild=discord.Object(id=849780703502532628))

    #Get guild roles
    print("Getting Guild Roles")
    Guild_Role_List = await guild_roles.Get(client, guild_id=ENV_GUILD)
    guild_roles.Display(Guild_Role_List)

    #Get guild members
    print("Getting Guild Members")
    Guild_Member_List = guild_members.Get(client, guild_id=ENV_GUILD);
    guild_members.Display(Guild_Member_List)

    #Secret ballots are message buttons, and a button only keeps working across a
    #restart if its view is re-registered by custom_id. Do that for every open one.
    Open_Ballots = [R for R in secret_store.Get().values() if not secret_store.Is_Closed(R)]
    for Ballot_Record in Open_Ballots:
        client.add_view(secret_view.Ballot(Ballot_Record["label"], Ballot_Record["answers"]))
    print("Re-registered % d open secret ballot(s)" % len(Open_Ballots))

    #Discord enforces a native poll's duration itself, but a secret ballot is ours
    #to close, so watch for expiry and publish the result when one runs out.
    client.loop.create_task(Close_Expired_Ballots())

    #Bot ready to perform async actions on demand
    print("Bot Ready!")

# Connect to discord using the bot's API Token
print("Connecting bot to discord")
client.run(ENV_TOKEN)