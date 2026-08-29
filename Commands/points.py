#Get the points sources for interactions
Points_Sources = sql_points.Points_Sources_Get(SQL_Cursor)
#remove the source_id = 1 entry (bot configuration)
Points_Sources = [Source for Source in Points_Sources if Source["source_id"] != 1]

#Management of points adjustment for a single, or multiple discord members via the generation of tokens
async def Points_Adjust(interaction: discord.Interaction, member: discord.Member, contribution: app_commands.Choice[int], level: app_commands.Choice[int], other_points: int, addition: bool) -> None:
	from Functions import bot_config
	#Variables accessible
	awarded_by = interaction.user.id
	source_id = contribution.value
	source_name = contribution.name
	level_id = level.value
	level_name = level.name
	action_word = "Awarded" if addition > 0 else "Deducted"
	manual_assignment = False if awarded_by == bot_config.env_get("DISCORD_USER") else True
	#Generate points token
	Token_ID = sql_points.Points_Token_Create(SQL_Connection, SQL_Cursor, source_id, awarded_by, manual_assignment)
	#Determine points value
	Points_Value = sql_points.Points_Get_Value(SQL_Cursor, source_id, level_id, addition, other_points)
	Transactions = sql_points.Points_Transaction_Insert(SQL_Connection, SQL_Cursor, Token_ID, member, Points_Value)
	await interaction.response.send_message(
		f"**Points {action_word}**\n"
		f"Token ID = {Token_ID}, Transactions = {Transactions}\n"
		f"User: {member.mention}\n"
		f"Points: {Points_Value}\n"
		f"Source: {source_name} ({source_id})\n"
		f"Tier: {level_name} ({level_id})\n"
		f"{action_word} by: <@{awarded_by}>"
	)

# Points subcommand group; appears in Discord as "/points <subcommand>"
Points_Group = app_commands.Group(name="points", description="Manage member points", guild_ids=[int(DISCORD_GUILD)])

#Command for adding points
@Points_Group.command(name="add", description="Add points to a single discord member")
@app_commands.describe(member="The Discord user having points awarded",	contribution="The reason for the points being granted", level="The tier of the award", other_points="For contribution 'Other' only, custom value of points to be added")
@app_commands.choices(
	level=[
		app_commands.Choice(name="Minor", value=1),
		app_commands.Choice(name="Standard", value=2),
		app_commands.Choice(name="Major", value=3),
	],
	contribution=[
		app_commands.Choice(name=Source["source_description"], value=Source["source_id"])
		for Source in Points_Sources
	]
)
async def points_add(interaction: discord.Interaction, member: discord.Member, contribution: app_commands.Choice[int], level: app_commands.Choice[int], other_points: int = 0) -> None:
	await Points_Adjust(interaction, member, contribution, level, other_points, True)

#Command for subtracting points
@Points_Group.command(name="subtract", description="Subtract points from a single discord member")
@app_commands.describe(member="The Discord user having points removed",	contribution="The reason for the points being removed", level="The tier of the deduction (for 'Other', this field contains the value of the points to be removed)", other_points="For contribution 'Other' only, custom value of points to be removed")
@app_commands.choices(
	level=[
		app_commands.Choice(name="Minor", value=1),
		app_commands.Choice(name="Standard", value=2),
		app_commands.Choice(name="Major", value=3),
	],
	contribution=[
		app_commands.Choice(name=Source["source_description"], value=Source["source_id"])
		for Source in Points_Sources
	]
)
async def points_subtract(interaction: discord.Interaction, member: discord.Member, contribution: app_commands.Choice[int], level: app_commands.Choice[int], other_points: int = 0) -> None:
	await Points_Adjust(interaction, member, contribution, level, other_points, False)

#Command for disabling points
@Points_Group.command(name="token_toggle_enable", description="Disable or enable all transactions relating to a specific transaction token id")
@app_commands.describe(token_id="The token ID relating to the points transaction being disabled or enabled", enabled="If enabling or disabling all transactions relating to this token id")
@app_commands.choices(
	enabled=[
		app_commands.Choice(name="Disable", value=0),
		app_commands.Choice(name="Enable", value=1),
	],
)
async def token_toggle_enable(interaction: discord.Interaction, enabled: app_commands.Choice[int], token_id: int) -> None:
	author_discord_id = interaction.user.id
	enabled_id = enabled.value
	enabled_name = enabled.name
	Token_Enabled = sql_points.Points_Token_Enabled_Toggle(SQL_Connection, SQL_Cursor, author_discord_id, token_id, enabled_id)
	action_word = "enabled" if enabled_id == 1 else "disabled"
	if Token_Enabled == None:
		await interaction.response.send_message(f"Token ID : {token_id} could not be found or is read only")
	elif Token_Enabled == False:
		await interaction.response.send_message(f"Token ID : {token_id} is already in the {action_word} state")
	elif Token_Enabled == True:
		await interaction.response.send_message(f"Token ID : {token_id} successfully {action_word}")

#Add command list for the points management
tree.add_command(Points_Group)