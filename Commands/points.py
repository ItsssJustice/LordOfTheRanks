#Get the points sources for interactions
Points_Sources = sql_points.Sources_Get(SQL_Cursor)
#remove the source_id = 1 entry (bot configuration)
Points_Sources = [Source for Source in Points_Sources if Source["source_id"] != 1]

# Class for handling UI components of Points_WOM_Competition
class Add_WOM_Competition_Confirm(discord.ui.View):
	def __init__(self, interaction: discord.Interaction, Competition_Data: dict, contribution: dict, level: dict, discord_ids: list, message_group: "bot_config.Message_Group"):
		super().__init__(timeout=120)
		self.original_interaction = interaction
		self.Competition_Data = Competition_Data
		self.contribution = contribution
		self.level = level
		self.discord_ids = discord_ids
		self.message_group = message_group

	async def on_timeout(self):
		# Disable buttons and let the moderator know the prompt expired
		for item in self.children:
			item.disabled = True
		try:
			await self.message_group.Edit("Confirmation timed out, no points were added.", view=self)
		except discord.NotFound:
			pass

	@discord.ui.button(label="Confirm", emoji="✅", style=discord.ButtonStyle.success)
	async def Confirm_Button(self, interaction: discord.Interaction, button: discord.ui.Button):
		# Only the moderator who ran the command can confirm
		if interaction.user.id != self.original_interaction.user.id:
			await interaction.response.send_message("Only the person who ran this command can confirm it.", ephemeral=True)
			return
		competition = self.Competition_Data["competition"]
		if not self.discord_ids:
			# No Points_Adjust call on this path, so this interaction must be
			# acknowledged here directly
			await interaction.response.defer()
			for item in self.children:
				item.disabled = True
			await self.message_group.Edit("⚠️ No linked Discord accounts found among participants — no points added.", view=self)
			self.stop()
			return
		# Resolve raw Discord IDs to Member objects
		members = []
		missing_members = []
		for discord_id in self.discord_ids:
			member = interaction.guild.get_member(discord_id)
			if member is None:
				try:
					member = await interaction.guild.fetch_member(discord_id)
				except discord.NotFound:
					missing_members.append(discord_id)
					continue
			members.append(member)
		if not members:
			# No Points_Adjust call on this path either, so acknowledge here
			await interaction.response.defer()
			for item in self.children:
				item.disabled = True
			await self.message_group.Edit("⚠️ None of the linked Discord accounts could be resolved to server members — no points added.", view=self)
			self.stop()
			return

		for item in self.children:
			item.disabled = True
		content = f"✅ Points added for **{len(members)}** participants in **{competition['title']}**."
		if missing_members:
			content += f"\n\n⚠️ {len(missing_members)} linked account(s) could not be found in the server and were skipped: {', '.join(str(m) for m in missing_members)}"
		# self.message_group edits the ORIGINAL slash-command interaction's
		# webhook - a different interaction/token to this button-click
		# interaction, so this does not consume `interaction`'s response slot
		await self.message_group.Edit(content, view=self)
		# Points_Adjust internally calls interaction.response.send_message(...),
		# which acknowledges THIS button-click interaction - do not defer or
		# respond to `interaction` anywhere above this line on this code path
		await Points_Adjust(interaction, self.contribution, self.level, members, 0, True)
		self.stop()

	@discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger)
	async def Cancel_Button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id != self.original_interaction.user.id:
			await interaction.response.send_message("Only the person who ran this command can cancel it.", ephemeral=True)
			return
		await interaction.response.defer()
		for item in self.children:
			item.disabled = True
		await self.message_group.Edit("❌ Points addition cancelled.", view=self)
		self.stop()

#Management of points adjustment for a single, or multiple discord members via the generation of tokens
async def Points_Adjust(interaction: discord.Interaction, contribution: app_commands.Choice[int], level: app_commands.Choice[int], member: discord.Member | list[discord.Member], other_points: int, addition: bool) -> None:
	#Verify user is a moderator to change another player's points
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, 1):
		await bot_config.Command_Permissions_Issue(interaction)
		return None
	#Normalize input to a list of members
	members = member if isinstance(member, list) else [member]
	if not members:
		await interaction.response.send_message("No members were provided to adjust points for.", ephemeral=True)
		return None
	#Variables accessible
	awarded_by = interaction.user.id
	source_id = contribution.value
	source_name = contribution.name
	level_id = level.value
	level_name = level.name
	action_word = "Awarded" if addition > 0 else "Deducted"
	manual_assignment = False if awarded_by == bot_config.env_get("DISCORD_USER") else True
	#Determine points value
	Points_Value = sql_points.Value_Get(SQL_Cursor, source_id, level_id, addition, other_points)
	if Points_Value is not None:
		#Generate points token
		Token_ID = sql_points.Token_Create(SQL_Connection, SQL_Cursor, source_id, awarded_by, manual_assignment)
		Transactions = sql_points.Transaction_Create(SQL_Connection, SQL_Cursor, Token_ID, members, Points_Value)
		#Format user list - single mention, or a line-by-line list for multiple members
		if len(members) == 1:
			user_lines = members[0].mention
		else:
			user_lines = "\n".join(f"- {m.mention}" for m in members)
		await interaction.response.send_message(
			f"**Points {action_word}**\n"
			f"Token ID = {Token_ID}, Transactions = {Transactions}\n"
			f"User(s):\n{user_lines}\n"
			f"Points: {Points_Value}\n"
			f"Source: {source_name} ({source_id})\n"
			f"Tier: {level_name} ({level_id})\n"
			f"{action_word} by: <@{awarded_by}>"
		)
	else:
		await interaction.response.send_message("Could not create a valid points token, please check the command input", ephemeral=True)
		return

async def Add_WOM_Competition(interaction: discord.Interaction, contribution: app_commands.Choice[int], level: app_commands.Choice[int], contribution_threshold: int = 0, competition_id: int = None):
	#Verify user is a moderator to change another player's points
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, 1):
		await bot_config.Command_Permissions_Issue(interaction)
		return None
	#Verify the points threshold specified is not 0
	if contribution_threshold == 0:
		await interaction.response.send_message("A contribution threshold value of 0 will add points to every clan member, please revise your command input", ephemeral=True)
		return None
	#Defer immediately - wom_data.Competition_Get and the SQL lookups below can
	#exceed Discord's 3-second interaction response window, which invalidates
	#the interaction token before we'd otherwise get a chance to respond
	await interaction.response.defer(ephemeral=True)
	#Gather the requested competition data
	Competition_Data = await wom_data.Competition_Get(WOM_USER, WOM_TOKEN, WOM_GUILD, competition_id, contribution_threshold)
	#Format the interactive response for the event host
	competition = Competition_Data["competition"]
	if not competition:
		await interaction.followup.send("No competition found.", ephemeral=True)
		return
	results = competition["results"]
	if not results:
		await interaction.followup.send("No results found.", ephemeral=True)
		return
	#Look up linked Discord accounts for every RSN in the results
	participant_ids = [result["player_id"] for result in results]
	Linked_Accounts = sql_account_link.Linked_Accounts_Get(SQL_Cursor, player_id=participant_ids)
	linked_lookup = {account["player_id"]: account["discord_id"] for account in Linked_Accounts}
	#Discord IDs only for RSNs that have a linked account
	discord_ids = [linked_lookup[result["player_id"]] for result in results if result["player_id"] in linked_lookup]
	#Create list of subtotals, showing linked Discord info or a warning if unlinked
	source_lines_parts = []
	for result in results:
		discord_id = linked_lookup.get(result["player_id"])
		if discord_id:
			member = interaction.guild.get_member(discord_id) if interaction.guild else None
			discord_display = f"{member.mention}" if member else f"<@{discord_id}>"
			source_lines_parts.append(f"{result['display_name']} — {discord_display}: {result['gained']}")
		else:
			source_lines_parts.append(f"⚠️ {result['display_name']} — `no discord linked`: {result['gained']}")
	source_lines = "\n".join(source_lines_parts)
	content = (
		f"**Points for Competition: {competition['title']}** (`{competition['competition_id']}`)\n"
		f"Start:  {competition['starts_at']} -  End: {competition['ends_at']}\n"
		f"Metric: {competition['metric']} - Participants: {len(results)}\n\n"
		f"{source_lines}\n\n"
		f"Runescape accounts with no discord linkage will be granted no points.\n"
		f"Confirm Points Addition?"
	)

	#Send response to event host for verification, splitting across messages if needed
	message_group = bot_config.Message_Group(interaction, ephemeral=True)
	view = Add_WOM_Competition_Confirm(interaction, Competition_Data, contribution, level, discord_ids, message_group)
	await message_group.Send(content, view=view)

#View a user's points
async def Points_View(interaction: discord.Interaction, member: discord.member = None, subtotals_to_display: int = 0):
	#Assert that if the discord id is blank, to use the current user
	if member is None:
		member = interaction.user
	#Allow a user to view their own points
	if interaction.user.id != member.id:
		#Verify user is a moderator to view another player's points
		if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, 1):
			await bot_config.Command_Permissions_Issue(interaction)
			return None
	Points = await sql_points.User_Total_Get(SQL_Connection, SQL_Cursor, member.id)
	if Points is None:
		await interaction.response.send_message("Could not display points totals, please check the command input", ephemeral=True)
		return
	#Sort subtotals
	subtotals = sorted(Points["subtotals"], key=lambda subtotal: subtotal["points"], reverse=True)
	if subtotals_to_display > 0:
		#ensure subtotals to display isn't larger than the number of subtotals available
		subtotals_to_display = min(subtotals_to_display, len(subtotals))
		subtotals = subtotals[:subtotals_to_display]
	#Create list of subtotals
	source_lines = "\n".join(
		f"{subtotal['source_description']}: {subtotal['points']}"
		for subtotal in subtotals
	)
	await interaction.response.send_message(
		f"**Points for {member.mention}** (`{member.id}`)\n"
		f"Total Points: {Points['total']}\n\n"
		f"{source_lines}", ephemeral=True,
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
	await Points_Adjust(interaction, contribution, level, member, other_points, True)

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
	await Points_Adjust(interaction, contribution, level, member, other_points, False)

#Command for adding points to a group of users from WOM competitions
@Points_Group.command(name="add_wom_competition", description="Add points to a group of people for a WOM competition")
@app_commands.describe(contribution_threshold="The number of KC / XP required to gain points", contribution="The reason for the points being granted", level="The tier of the award", competition_id="WOM Competition ID")
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
async def add_wom_competition(interaction: discord.Interaction, contribution: app_commands.Choice[int], level: app_commands.Choice[int], contribution_threshold: int = 0, competition_id: int = 0) -> None:
	await Add_WOM_Competition(interaction, contribution, level, contribution_threshold, competition_id)

#Command for viewing points for a user
@Points_Group.command(name="view", description="View points for a single discord member")
@app_commands.describe(member="The Discord user inspected to view their points")
async def points_view(interaction: discord.Interaction, member: discord.Member = None, subtotals_display: int = 3) -> None:
	await Points_View(interaction, member, subtotals_display)

#Command for enabling/disabling points
@Points_Group.command(name="token_toggle_enable", description="Disable or enable all transactions relating to a specific transaction token id")
@app_commands.describe(token_id="The token ID relating to the points transaction being disabled or enabled", enabled="If enabling or disabling all transactions relating to this token id")
@app_commands.choices(
	enabled=[
		app_commands.Choice(name="Disable", value=0),
		app_commands.Choice(name="Enable", value=1),
	],
)
async def token_toggle_enable(interaction: discord.Interaction, enabled: app_commands.Choice[int], token_id: int) -> None:
	#Verify user is a moderator to enable/disable points tokens
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, 1):
		await bot_config.Command_Permissions_Issue(interaction)
		return None
	author_discord_id = interaction.user.id
	enabled_id = enabled.value
	enabled_name = enabled.name
	Token_Enabled = sql_points.Token_Toggle_Enable(SQL_Connection, SQL_Cursor, author_discord_id, token_id, enabled_id)
	action_word = "enabled" if enabled_id == 1 else "disabled"
	if Token_Enabled == None:
		await interaction.response.send_message(f"Token ID : {token_id} could not be found or is read only")
	elif Token_Enabled == False:
		await interaction.response.send_message(f"Token ID : {token_id} is already in the {action_word} state")
	elif Token_Enabled == True:
		await interaction.response.send_message(f"Token ID : {token_id} successfully {action_word}")

#Add command list for the points management
tree.add_command(Points_Group)