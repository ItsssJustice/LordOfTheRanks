#Get the points sources for interactions
Points_Sources = sql_points.Sources_Get(SQL_Cursor)
#remove the source_id = 1 entry (bot configuration)
Points_Sources = [Source for Source in Points_Sources if Source["source_id"] != 1]

#Management of points adjustment for a single, or multiple discord members via the generation of tokens
async def Points_Adjust(interaction: discord.Interaction, contribution: app_commands.Choice[int], level: app_commands.Choice[int], member: discord.Member | list[discord.Member], other_points: int, addition: bool) -> None:
	#Verify user is a moderator to change another player's points
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, 1):
		await bot_config.Command_Permissions_Issue(interaction)
		return None
	#Normalize input to a list of members
	members = member if isinstance(member, list) else [member]
	if not members:
		Embed = embed_handling.Build(
			title="Points Adjustment Failed",
			description="No members were provided to adjust points for.",
			colour=discord.Colour.red()
		)
		await embed_handling.Send(interaction, Embed, ephemeral=True)
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
			User_Lines = members[0].mention
		else:
			User_Lines = "\n".join("- %s" % m.mention for m in members)
			Embed = embed_handling.Build(
			title="Points %s" % action_word,
			colour=discord.Colour.green() if addition else discord.Colour.red(),
			fields=[
					("%s by" % action_word, "<@%d>" % awarded_by, True),
					("Token ID", "%d" % (Token_ID), True),
					("Transactions", "%d" % (Transactions), True),
					("Points", str(Points_Value), True),
					("Source", "%s" % (source_name), True),
					("Tier", "%s" % (level_name), True),
					("User(s)", User_Lines, False),
				]
			)
			await embed_handling.Send(interaction, Embed)
	else:
		Embed = embed_handling.Build(
			title="Points Adjustment Failed",
			description="Could not create a valid points token, please check the command input.",
			colour=discord.Colour.red()
		)
		await embed_handling.Send(interaction, Embed, ephemeral=True)
		return

async def Add_WOM_Competition(interaction: discord.Interaction, contribution: app_commands.Choice[int], level: app_commands.Choice[int], contribution_threshold: int = 0, competition_id: int = None):
	#Verify user is a moderator to change another player's points
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, 1):
		await bot_config.Command_Permissions_Issue(interaction)
		return None
	#Verify the points threshold specified is not 0
	if contribution_threshold == 0:
		Embed = embed_handling.Build(
			title="Invalid Contribution Threshold",
			description="A contribution threshold value of 0 will add points to every clan member, please revise your command input.",
			colour=discord.Colour.red()
		)
		await embed_handling.Send(interaction, Embed, ephemeral=True)
		return None
	#Defer immediately - wom_data.Competition_Get and the SQL lookups below can
	#exceed Discord's 3-second interaction response window, which invalidates
	#the interaction token before we'd otherwise get a chance to respond
	await interaction.response.defer(ephemeral=True)
	#Gather the requested competition data
	Competition_Data = await wom_data.Competition_Get(WOM_USER, WOM_TOKEN, WOM_GUILD, competition_id, contribution_threshold)
	competition = Competition_Data["competition"]
	if not competition:
		Embed = embed_handling.Build(title="No Competition Found", colour=discord.Colour.red())
		await embed_handling.Send(interaction, Embed, ephemeral=True)
		return
	results = competition["results"]
	if not results:
		Embed = embed_handling.Build(title="No Results Found", colour=discord.Colour.red())
		await embed_handling.Send(interaction, Embed, ephemeral=True)
		return

	#Look up linked Discord accounts for every RSN in the results
	participant_ids = [result["player_id"] for result in results]
	Linked_Accounts = sql_account_link.Linked_Accounts_Get(SQL_Cursor, player_id=participant_ids)
	linked_lookup = {account["player_id"]: account["discord_id"] for account in Linked_Accounts}
	#Discord IDs only for RSNs that have a linked account
	discord_ids = [linked_lookup[result["player_id"]] for result in results if result["player_id"] in linked_lookup]

	#Build an aligned, monospaced table of who will receive points, rather than one field per
	#participant - RSN | Discord | Competition Gain.
	Table_Rows = []
	for result in results:
		discord_id = linked_lookup.get(result["player_id"])
		if discord_id:
			member = interaction.guild.get_member(discord_id) if interaction.guild else None
			Discord_Cell = member.display_name if member else str(discord_id)
		else:
			#Bold markdown does not render inside a fenced code block (discord does not parse
			#markdown there), so the warning triangle plus uppercase stands in for emphasis while
			#keeping the row's width predictable for column alignment.
			Discord_Cell = "⚠ NOT LINKED"
		Table_Rows.append((result["display_name"], Discord_Cell, str(result["gained"])))

	Headers = ("RSN", "Discord", "Competition Gain")
	Column_Widths = [
		max(len(Headers[i]), max((len(Row[i]) for Row in Table_Rows), default=0))
		for i in range(3)
	]

	def _Format_Row(Row):
		return "  ".join(Cell.ljust(Column_Widths[i]) for i, Cell in enumerate(Row))

	Header_Line = _Format_Row(Headers)
	Separator_Line = "  ".join("-" * Width for Width in Column_Widths)

	#Chunked across pages so no single embed breaches discord's 4096 character description
	#limit - Build would otherwise silently trim the table mid-row.
	Rows_Per_Page = 20
	Row_Chunks = [Table_Rows[i:i + Rows_Per_Page] for i in range(0, len(Table_Rows), Rows_Per_Page)] or [[]]
	Page_Count = len(Row_Chunks)

	Pages = []
	for Page_Index, Chunk in enumerate(Row_Chunks):
		Table_Lines = [Header_Line, Separator_Line] + [_Format_Row(Row) for Row in Chunk]
		Table_Block = "```\n%s\n```" % "\n".join(Table_Lines)
		Description = (
			"Start: %s  -  End: %s\nMetric: %s  -  Participants: %d\n\n"
			"Runescape accounts with no discord linkage will be granted no points.\n\n"
			"%s\n\nConfirm Points Addition?"
			% (competition["starts_at"], competition["ends_at"], competition["metric"],
			   len(results), Table_Block)
		)
		Pages.append(embed_handling.Build(
			title="Points for Competition: %s" % competition["title"],
			description=Description,
			colour=discord.Colour.blurple(),
			footer=("Page %d/%d" % (Page_Index + 1, Page_Count)) if Page_Count > 1 else None
		))

	#The two extra buttons attached below. embed_handling only renders these and dispatches their
	#clicks - all of the actual confirm/cancel behaviour lives here, as closures over this call's
	#contribution/level/discord_ids/competition.
	async def _Confirm_Clicked(Click_Interaction: discord.Interaction, View):
		for Item in View.children:
			Item.disabled = True
		if not discord_ids:
			Result_Embed = embed_handling.Build(
				title="Points Addition Cancelled",
				description="⚠️ No linked Discord accounts found among participants — no points added.",
				colour=discord.Colour.orange()
			)
			await Click_Interaction.response.defer()
			await embed_handling.Update(View, Result_Embed, New_View=View)
			View.stop()
			return
		#Resolve raw Discord IDs to Member objects
		Members = []
		Missing_Members = []
		for discord_id in discord_ids:
			member = interaction.guild.get_member(discord_id)
			if member is None:
				try:
					member = await interaction.guild.fetch_member(discord_id)
				except discord.NotFound:
					Missing_Members.append(discord_id)
					continue
			Members.append(member)
		if not Members:
			Result_Embed = embed_handling.Build(
				title="Points Addition Cancelled",
				description="⚠️ None of the linked Discord accounts could be resolved to server members — no points added.",
				colour=discord.Colour.orange()
			)
			await Click_Interaction.response.defer()
			await embed_handling.Update(View, Result_Embed, New_View=View)
			View.stop()
			return
		#Participants with no linked discord account at all - never made it into discord_ids
		#in the first place, so they never had a chance to fail resolution above either.
		Unlinked_Count = len(results) - len(discord_ids)
		Result_Fields = []
		if Missing_Members:
			Result_Fields.append(("Skipped (no discord account linked)",", ".join(str(m) for m in Missing_Members), False))
		if Unlinked_Count:
			Result_Fields.append(("Skipped (no linked account)", str(Unlinked_Count), False))
		Description = "✅ Points added for **%d** participant(s) in **%s**." % (len(Members), competition["title"])
		if Unlinked_Count:
			Description += "\n⚠️ **%d** participant(s) skipped — no linked Discord account." % Unlinked_Count
		Result_Embed = embed_handling.Build(
			title="Points Added",
			description=Description,
			colour=discord.Colour.green(),
			fields=Result_Fields
		)
		#Edits the confirm dialog's OWN message via embed_handling.Embed_Update (a webhook edit),
		#not Click_Interaction.response - that keeps this click's response slot free for
		#Points_Adjust below, which sends its own separate confirmation message using the same
		#interaction. Do not defer or respond to Click_Interaction anywhere above this line.
		await embed_handling.Update(View, Result_Embed, New_View=View)
		await Points_Adjust(Click_Interaction, contribution, level, Members, 0, True)
		View.stop()

	async def _Cancel_Clicked(Click_Interaction: discord.Interaction, View):
		for Item in View.children:
			Item.disabled = True
		Result_Embed = embed_handling.Build(
			title="Points Addition Cancelled",
			description="❌ Cancelled by %s." % Click_Interaction.user.mention,
			colour=discord.Colour.red()
		)
		await Click_Interaction.response.defer()
		await embed_handling.Update(View, Result_Embed, New_View=View)
		View.stop()

	#"cancel": True tells Embed_Paginator_View to put this button in the Stop button's own slot
	#instead of adding it as a fourth item.
	Extra_Buttons = [
		{"label": "Confirm", "emoji": "✅", "style": discord.ButtonStyle.success, "callback": _Confirm_Clicked},
		{"label": "Cancel", "emoji": "❌", "style": discord.ButtonStyle.danger, "callback": _Cancel_Clicked, "cancel": True},
	]

	#interaction_check on the view embed_handling builds already restricts these buttons to
	#interaction.user - the moderator who ran this command - so no separate author check is
	#needed in the callbacks above.
	await embed_handling.Send(interaction, Pages, ephemeral=True, extra_buttons=Extra_Buttons, timeout=120)

#View a user's points
async def Points_View(interaction: discord.Interaction, member: discord.Member = None, subtotals_to_display: int = 0):
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
		Embed = embed_handling.Build(
			title="Points Lookup Failed",
			description="Could not display points totals, please check the command input.",
			colour=discord.Colour.red()
		)
		await embed_handling.Send(interaction, Embed, ephemeral=True)
		return
	#Sort subtotals
	subtotals = sorted(Points["subtotals"], key=lambda subtotal: subtotal["points"], reverse=True)
	if subtotals_to_display > 0:
		#ensure subtotals to display isn't larger than the number of subtotals available
		subtotals_to_display = min(subtotals_to_display, len(subtotals))
		subtotals = subtotals[:subtotals_to_display]
	Fields = [(subtotal["source_description"], str(subtotal["points"]), True) for subtotal in subtotals]
	Embed = embed_handling.Build(
		title="Points for %s" % member.display_name,
		description="Total Points: **%d**" % Points["total"],
		colour=discord.Colour.blurple(),
		#thumbnail_url=member.display_avatar.url,
		fields=Fields
	)
	await embed_handling.Send(interaction, Embed, ephemeral=True)

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
	Token_Enabled = sql_points.Token_Toggle_Enable(SQL_Connection, SQL_Cursor, author_discord_id, token_id, enabled_id)
	action_word = "enabled" if enabled_id == 1 else "disabled"
	if Token_Enabled is None:
		Embed = embed_handling.Build(
			title="Token Not Found",
			description="Token ID `%d` could not be found or is read only." % token_id,
			colour=discord.Colour.red()
		)
	elif Token_Enabled is False:
		Embed = embed_handling.Build(
			title="No Change",
			description="Token ID `%d` is already in the %s state." % (token_id, action_word),
			colour=discord.Colour.orange()
		)
	else:
		Embed = embed_handling.Build(
			title="Token Updated",
			description="Token ID `%d` successfully %s." % (token_id, action_word),
			colour=discord.Colour.green()
		)
	await embed_handling.Send(interaction, Embed, ephemeral=True)

#Add command list for the points management
tree.add_command(Points_Group)