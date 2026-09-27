def Account_Line(RSN, Player_Id, Is_Main, Locked):
    Marker = "⭐" if Is_Main else "▫️"
    Lock_Note = " 🔒 locked" if Locked else ""
    return "%s **%s** (`%d`)%s" % (Marker, RSN, Player_Id, Lock_Note)

def Linked_Accounts_List(Member, Links, RSN_Lookup):
    """Member: the discord.Member being displayed.
       Links: list of dicts from Linked_Accounts_Get.
       RSN_Lookup: {player_id: current_rsn}."""
    if not Links:
        return "%s has no linked OSRS accounts." % Member.mention
    # Main account first, then alphabetical, so it reads as "here's the one that
    # matters, then everything else" rather than database order.
    Ordered = sorted(Links, key=lambda L: (not L["is_main_account"], RSN_Lookup.get(L["player_id"], "").lower()))
    Lines = ["**Linked OSRS accounts for %s**" % Member.display_name]
    for L in Ordered:
        RSN = RSN_Lookup.get(L["player_id"], "Unknown RSN")
        Lines.append(Account_Line(RSN, L["player_id"], L["is_main_account"], L["moderator_locked"]))
    return "\n".join(Lines)

_Unlinked_Titles = {
    "conflicts": "Conflicting matches (ambiguous RSN)",
    "unmatched_osrs": "OSRS accounts with no Discord match",
    "repaired_needed": "Links needing repair",
}

def Unlinked_Accounts_List(Method, Records, RSN_Lookup):
    """Records: one bucket's list from Linked_Accounts_Attempt_Matches's return dict.
       RSN_Lookup: {player_id: current_rsn}."""
    Title = _Unlinked_Titles.get(Method, Method)
    if not Records:
        return "**%s** - nothing to show." % Title

    Lines = ["**%s** (%d)" % (Title, len(Records))]
    for R in Records:
        Player_Id = R.get("player_id")
        RSN = RSN_Lookup.get(Player_Id, "Unknown RSN") if Player_Id is not None else "N/A"
        Discord_Part = ("<@%d>" % R["discord_id"]) if R.get("discord_id") else "_no discord match_"
        Line = "▫️ **%s** (`%s`) - %s" % (RSN, Player_Id, Discord_Part)
        if R.get("reason"):
            Line += "  _(%s)_" % R["reason"]
        Lines.append(Line)
    return "\n".join(Lines)

async def Link_Update(interaction: discord.Interaction, member: discord.Member, runescape_name: str = None, is_main_account: bool = False) -> None:
	Player_Id = sql_account_osrs.Runescape_Name_To_Player_ID(SQL_Cursor, runescape_name, discord_id=member.id)
	Message = None
	Result = None
	if Player_Id is None:
		Message = f"No OSRS clan member found with an RSN close enough to '{runescape_name}'."
	elif Player_Id is False:
		Message = f"'{runescape_name}' is already linked to another Discord account, please contact a moderator if you believe this is incorrect."
	else:
		Result = await sql_account_link.Linked_Accounts_Update(SQL_Connection, SQL_Cursor, member.id, Player_Id, is_main_account, caller_id=interaction.user.id)
		if Result is None:
			Message = "Could not update the link, please check the command input."
		elif Result == "permission_denied":
			Message = await bot_config.Command_Permissions_Issue(interaction, False)
		elif Result == "owned_by_another":
			Message = "This OSRS account is already linked to another Discord account, please contact a moderator if you believe this is incorrect."
		elif Result == "locked":
			Message = "This account can only be modified by a moderator, please contact a moderator to resolve this issue."
	if Message is not None:
		await interaction.response.send_message(Message, ephemeral=True)
		return None
	Link_Id = Result
	await interaction.response.send_message(f"Linked {member.mention} to RSN '{runescape_name}' (player_id {Player_Id}).", ephemeral=True)
	await bot_config.Notify_Channel(interaction.client, DISCORD_NOTIFICATION_CHANNEL_ACCOUNT_LINK, f"🔗 {interaction.user.mention} linked {member.mention} to RSN '{runescape_name}' (player_id {Player_Id}).")
	return Link_Id


async def Link_Delete(interaction: discord.Interaction, member: discord.Member, runescape_name: str = None) -> None:
	# Require_Unlinked=False: for deletion the RSN being already linked is the
	# expected case, not an error.
	Player_Id = sql_account_osrs.Runescape_Name_To_Player_ID(SQL_Cursor, runescape_name, Require_Unlinked=False)
	Message = None
	Result = None
	if Player_Id is None:
		Message = f"No OSRS clan member found with an RSN close enough to '{runescape_name}'."
	else:
		Result = await sql_account_link.Linked_Accounts_Delete(SQL_Connection, SQL_Cursor, member.id, Player_Id, caller_id=interaction.user.id)
		if Result is None:
			Message = "Could not delete the link, please check the command input."
		elif Result == "permission_denied":
			Message = await bot_config.Command_Permissions_Issue(interaction, False)
		elif Result == "not_found":
			Message = f"'{runescape_name}' is not linked to {member.mention}."
		elif Result == "final_account":
			Message = "You cannot delete the final linked OSRS account."
		elif Result == "locked":
			Message = "This account can only be modified by a moderator, please contact a moderator to resolve this issue."
	if Message is not None:
		await interaction.response.send_message(Message, ephemeral=True)
		return None
	Link_Id = Result
	await interaction.response.send_message(f"Unlinked RSN '{runescape_name}' (player_id {Player_Id}) from {member.mention}.", ephemeral=True)
	await bot_config.Notify_Channel(interaction.client, DISCORD_NOTIFICATION_CHANNEL_ACCOUNT_LINK, f"🔗 {interaction.user.mention} unlinked RSN '{runescape_name}' (player_id {Player_Id}) from {member.mention}.")
	return Link_Id


async def Link_Set_Main(interaction: discord.Interaction, member: discord.Member, runescape_name: str = None) -> None:
	Player_Id = sql_account_osrs.Runescape_Name_To_Player_ID(SQL_Cursor, runescape_name, discord_id=member.id, Own_Only=True)
	Message = None
	Result = None
	if Player_Id is False:
		Message = f"No RSN linked to {member.mention} is close enough to '{runescape_name}'."
	else:
		Result = await sql_account_link.Linked_Accounts_Set_Main(SQL_Connection, SQL_Cursor, member.id, Player_Id, caller_id=interaction.user.id)
		if Result is None:
			Message = "Could not update the main account, please check the command input."
		elif Result == "permission_denied":
			Message = await bot_config.Command_Permissions_Issue(interaction, False)
		elif Result == "locked":
			Message = "This account can only be modified by a moderator, please contact a moderator to resolve this issue."
		elif Result == "not_found":
			Message = f"No RSN linked to {member.mention} is close enough to '{runescape_name}'."
		elif Result == "already_main":
			Message = f"'{runescape_name}' is already {member.mention}'s main account."
	if Message is not None:
		await interaction.response.send_message(Message, ephemeral=True)
		return None
	Links = sql_account_link.Linked_Accounts_Get(SQL_Cursor, discord_id=member.id, player_id=None) or []
	Osrs_Members = sql_account_osrs.Members_Get(SQL_Cursor) or []
	RSN_Lookup = {M["player_id"]: M["current_rsn"] for M in Osrs_Members}
	Message = "Main account changed for %s:\n%s" % (member.mention, Linked_Accounts_List(member, Links, RSN_Lookup))
	await interaction.response.send_message(Message, ephemeral=True)
	await bot_config.Notify_Channel(interaction.client, DISCORD_NOTIFICATION_CHANNEL_ACCOUNT_LINK, f"⭐ {interaction.user.mention} set {member.mention}'s main account to RSN '{runescape_name}'.")
	return Result

async def Link_Lock(interaction: discord.Interaction, member: discord.Member) -> None:
	Result = await sql_account_link.Linked_Accounts_Lock_Toggle(SQL_Connection, SQL_Cursor, member.id, caller_id=interaction.user.id)
	Message = None
	if Result is None:
		Message = "Could not toggle the lock, please check the command input."
	elif Result == "permission_denied":
		Message = await bot_config.Command_Permissions_Issue(interaction, False)
	elif Result == "not_found":
		Message = f"{member.mention} has no linked OSRS accounts to lock."
	if Message is not None:
		await interaction.response.send_message(Message, ephemeral=True)
		return None
	await interaction.response.send_message(f"{member.mention}'s linked accounts are now **{Result}**.", ephemeral=True)
	await bot_config.Notify_Channel(interaction.client, DISCORD_NOTIFICATION_CHANNEL_ACCOUNT_LINK, f"🔒 {interaction.user.mention} set {member.mention}'s linked accounts to **{Result}**.")
	return Result

async def Link_View(interaction: discord.Interaction, member: discord.Member = None) -> None:
	Display_Member = member if member is not None else interaction.user
	Links = sql_account_link.Linked_Accounts_Get(SQL_Cursor, discord_id=Display_Member.id, player_id=None) or []
	RSN_Lookup = {}
	if Links:
		Osrs_Members = sql_account_osrs.Members_Get(SQL_Cursor) or []
		RSN_Lookup = {M["player_id"]: M["current_rsn"] for M in Osrs_Members}
		Message = Linked_Accounts_List(Display_Member, Links, RSN_Lookup)
	else:
		Message = "No linked OSRS accounts found, please add an account or contact a moderator."
	await interaction.response.send_message(Message, ephemeral=True)

#Display lists of OSRS accounts that need linking to discord
async def Unlinked_View(interaction: discord.Interaction, method: str) -> None:
	Valid_Methods = ("conflicts", "unmatched_osrs", "repaired_needed")
	if method not in Valid_Methods:
		await interaction.response.send_message(
			"Method must be one of: %s." % ", ".join(Valid_Methods), ephemeral=True)
		return
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, 1):
		await bot_config.Command_Permissions_Issue(interaction)
		return
	# Attempt_Matches pulls and cross-references the whole membership, so buy
	# ourselves some time rather than risk the 3-second interaction timeout.
	# Not ephemeral: this is meant to be visible to the whole channel.
	await interaction.response.defer(ephemeral=False)
	Discord_Members = sql_account_discord.Members_Get(SQL_Cursor) or []
	Osrs_Members = sql_account_osrs.Members_Get(SQL_Cursor) or []
	Link_Data = sql_account_link.Linked_Accounts_Attempt_Matches(SQL_Cursor, Discord_Members, Osrs_Members)
	Records = Link_Data.get(method, [])
	RSN_Lookup = {M["player_id"]: M["current_rsn"] for M in Osrs_Members}
	Body = Unlinked_Accounts_List(method, Records, RSN_Lookup)
	# Discord limits a single message to 2000 characters; split well before that
	# so a long list of conflicts/repairs doesn't get rejected outright.
	Chunks, Current = [], ""
	for Line in Body.split("\n"):
		if len(Current) + len(Line) + 1 > 1900:
			Chunks.append(Current)
			Current = ""
		Current += Line + "\n"
	Chunks.append(Current)
	for Chunk in Chunks:
		await interaction.followup.send(Chunk, ephemeral=False)


# Points subcommand group; appears in Discord as "/Linked_Accounts <subcommand>"
Links_Group = app_commands.Group(name="linked_accounts", description="Manage OSRS RSN and Discord links", guild_ids=[int(DISCORD_GUILD)])
#Command for adding points
@Links_Group.command(name="add_or_update", description="Add or Update a link between a discord member and RSN")
async def link_add(interaction: discord.Interaction, member: discord.Member = None, runescape_name: str = None, is_main_account: bool = False) -> None:
	#Leaving member out means the caller's own links, as set_main_rsn and view do
	await Link_Update(interaction, member if member is not None else interaction.user, runescape_name, is_main_account)

@Links_Group.command(name="delete", description="Delete a link between a discord member and RSN")
async def link_delete(interaction: discord.Interaction, member: discord.Member = None, runescape_name: str = None) -> None:
	#Leaving member out means the caller's own links, as set_main_rsn and view do
	await Link_Delete(interaction, member if member is not None else interaction.user, runescape_name)

@Links_Group.command(name="toggle_lock", description="Lock changing or deleting account links for a specific discord id")
async def link_lock(interaction: discord.Interaction, member: discord.Member) -> None:
	await Link_Lock(interaction, member)

@Links_Group.command(name="set_main_rsn", description="Set an already linked OSRS account as a main")
async def set_main(interaction: discord.Interaction, member: discord.Member = None, runescape_name: str = None) -> None:
	await Link_Set_Main(interaction, member if member is not None else interaction.user, runescape_name)

@Links_Group.command(name="view", description="View links between a discord member and RSN")
async def link_view(interaction: discord.Interaction, member: discord.Member = None) -> None:
	await Link_View(interaction, member)

@Links_Group.command(name="unlinked_view", description="View OSRS accounts that need a moderator's attention to fix their linkages to discord")
@app_commands.describe(method="Which category to display")
@app_commands.choices(
	method=[
	app_commands.Choice(name="Conflicts (ambiguous matches)", value="conflicts"),
	app_commands.Choice(name="Unmatched OSRS accounts", value="unmatched_osrs"),
	app_commands.Choice(name="Needs repair", value="repaired_needed"),
])
async def unlinked_view(interaction: discord.Interaction, method: app_commands.Choice[str]) -> None:
	await Unlinked_View(interaction, method.value)

tree.add_command(Links_Group)