#Get an env variable including required imports, for use inside functions to reduce duplicated imports
def env_get(Variable):
	import os
	import json
	return str(os.getenv(Variable))

async def Command_Permissions_Issue(interaction):
	await interaction.response.send_message("You do not have the correct permissions execute this command with the inputs supplied.", ephemeral=True)