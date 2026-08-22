
# Import core libraries
import os
import importlib
import discord
import dotenv
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
ENV_TOKEN = str(os.getenv("TOKEN"))
#Homeland's server UUID; ensures nobody else can use the bot to avoid conflicts if other servers get access to it for whatever reason (as we're not making a universal product)
ENV_GUILD = str(os.getenv("GUILD"))

# Namespace variables required to execute command code
Command_Namespace = {
    "tree": tree,
    "discord": discord,
    "app_commands": discord.app_commands,
    "ENV_GUILD": ENV_GUILD
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
    await tree.sync(guild=discord.Object(id=849780703502532628))

    #Get guild roles
    print("Getting Guild Roles")
    Guild_Role_List = await guild_roles.Get(client, guild_id=ENV_GUILD)
    guild_roles.Display(Guild_Role_List)

    #Get guild members
    print("Getting Guild Members")
    Guild_Member_List = guild_members.Get(client, guild_id=ENV_GUILD);
    guild_members.Display(Guild_Member_List)

    #Bot ready to perform async actions on demand
    print("Bot Ready!")

# Connect to discord using the bot's API Token
print("Connecting bot to discord")
client.run(ENV_TOKEN)