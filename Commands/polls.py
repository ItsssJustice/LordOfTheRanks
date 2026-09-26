async def Create(interaction: discord.Interaction, channel: discord.TextChannel, question: str, answers: str, hours: int = 24, multiple: bool = False):
	Answer_List = [O.strip() for O in answers.split("|") if O.strip()]
	if len(Answer_List) < 2 or len(Answer_List) > 25:
		await interaction.response.send_message(
			"A poll needs between 2 and 25 answers, I counted % d. Separate them with |"
			% len(Answer_List), ephemeral=True)
		return
	Too_Long = [O for O in Answer_List if len(O) > 80]
	if Too_Long:
		await interaction.response.send_message(
			"Answers max out at 80 characters: " + ", ".join(Too_Long), ephemeral=True)
		return
	if len(question) > 255:
		await interaction.response.send_message(
			"The question must be 255 characters or fewer, that one is %d." % len(question),
			ephemeral=True)
		return
	if hours < 1 or hours > 768:
		await interaction.response.send_message("Duration must be 1 to 768 hours.", ephemeral=True)
		return
	Record = poll_store.Create(SQL_Connection, SQL_Cursor, channel.id, interaction.user.id, question, Answer_List, multiple, hours)
	try:
		Message = await channel.send(
			embed=poll_view.Build_Embed(Record),
			view=poll_view.Poll_Buttons(SQL_Connection, SQL_Cursor, Record["poll_id"], Answer_List))
	except discord.Forbidden:
		await interaction.response.send_message(
			"I'm missing permissions in % s. I need 'View Channel' and 'Send Messages' there."
			% channel.mention, ephemeral=True)
		return
	poll_store.Attach_Message(SQL_Connection, SQL_Cursor, Record["poll_id"], Message.id)
	Key = poll_store.Poll_Key_Encode(Record["poll_id"])
	await interaction.response.send_message(
		"Poll `% s` posted in % s.\nRead it back later with `/pollresults poll_id:% s`\n%s%s"
		% (Key, channel.mention, Key, Message.jump_url,
		   poll_view.Emoji_Warning(interaction.client, question, answers)),
		ephemeral=True)

async def End(interaction: discord.Interaction, poll_id: str):
	Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
	if Record is None:
		await interaction.response.send_message("No poll with ID '% s'." % poll_id, ephemeral=True)
		return
	if poll_store.Is_Closed(Record):
		await interaction.response.send_message("That poll is already closed.", ephemeral=True)
		return
	await interaction.response.defer(ephemeral=True)
	Record = poll_store.Close(SQL_Connection, SQL_Cursor, Record["poll_id"])
	await poll_view.Refresh_Message(SQL_Connection, SQL_Cursor, interaction.client, Record)
	Tally, Voter_Count = poll_store.Tally(Record)
	Lines = ["Closed %s" % poll_view.Reference(Record),
			 "%d member(s) voted" % Voter_Count]
	for Text, Count in Tally:
		Lines.append("  %d - %s" % (Count, Text))
	Lines.append(poll_format.Outcome(Tally))
	await interaction.followup.send("\n".join(Lines), ephemeral=True)

async def Results(interaction: discord.Interaction, poll_id: str):
	Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
	if Record is None:
		Known = [Key for Key, _ in poll_store.Recent_Choices(SQL_Cursor)][:10]
		await interaction.response.send_message(
			"No poll with ID '% s'. Recent poll ID(s): % s"
			% (poll_id, ", ".join(Known) if Known else "none yet"),
			ephemeral=True)
		return
	if not poll_store.Is_Closed(Record):
		Closes = discord.utils.format_dt(poll_store.As_Aware(Record["closes_at"]), "R")
		await interaction.response.send_message(
			"**% s** is still open. Results are shown once voting closes, %s."
			% (Record["question"], Closes), ephemeral=True)
		return
	Tally, Voter_Count = poll_store.Tally(Record)
	Total = sum(Count for _, Count in Tally)
	Lines = [poll_view.Reference(Record),
			 "_Closed_ | %d vote(s) from %d member(s)" % (Total, Voter_Count), ""]
	for Text, Count in Tally:
		Lines.append(poll_format.Result_Line(Text, Count, Total))
	Lines.append("")
	Lines.append(poll_format.Outcome(Tally))
	await interaction.response.send_message("\n".join(Lines), ephemeral=True)

async def Results_Detailed(interaction: discord.Interaction, poll_id: str, force: bool = False):
	Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
	if Record is None:
		await interaction.response.send_message("No poll with ID '% s'." % poll_id, ephemeral=True)
		return
	if not poll_store.Is_Closed(Record) and not force:
		Closes = discord.utils.format_dt(poll_store.As_Aware(Record["closes_at"]), "R")
		await interaction.response.send_message(
			"**% s** is still open, closing %s.\nClose it with `/pollend poll_id:% s`, or pass "
			"`force:True` to see the breakdown now."
			% (Record["question"], Closes, poll_id), ephemeral=True)
		return
	# One member lookup per voter, so buy ourselves some time
	await interaction.response.defer(ephemeral=True)
	Guild = interaction.client.get_guild(int(DISCORD_GUILD)) or interaction.guild
	Lines = [poll_view.Reference(Record)]
	Lines.append("_% s_" % ("Closed" if poll_store.Is_Closed(Record) else "Still open"))
	Lines.append("")
	for Text, User_Ids in poll_store.Voters_By_Answer(Record):
		Lines.append("**%s** - %d" % (Text, len(User_Ids)))
		if not User_Ids:
			Lines.append("  _nobody_")
		else:
			Names = []
			for User_Id in User_Ids:
				Member = await poll_members.Resolve_Member(Guild, User_Id)
				Names.append(Member.display_name if Member else "unknown (%d)" % User_Id)
			Lines.append("  " + ", ".join(Names))
		Lines.append("")
	# A clan-sized poll can blow past discord's 2000 character message limit
	Body = "\n".join(Lines)
	Chunks, Current = [], ""
	for Line in Body.split("\n"):
		if len(Current) + len(Line) + 1 > 1900:
			Chunks.append(Current); Current = ""
		Current += Line + "\n"
	Chunks.append(Current)
	for Chunk in Chunks:
		await interaction.followup.send(Chunk, ephemeral=True)

async def Grant(interaction: discord.Interaction, poll_id: str, apply: bool = False, force: bool = False):
	Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
	if Record is None:
		await interaction.response.send_message("No poll with ID '% s'." % poll_id, ephemeral=True)
		return
	await interaction.response.defer(ephemeral=True)
	# Guard on the vote being a rank vote, not merely on it naming somebody: this
	# command reads answers[0] as the affirmative, which only holds for the Yes/No
	# pair a rank vote is built from.
	Subject_Id = Record.get("subject_id")
	if not Subject_Id or not poll_store.Is_Rank_Vote(Record):
		await interaction.followup.send(
			"**% s** is a generic poll, so there is nobody to apply it to.\n"
			"Only votes started with `/startpromotionvote` or `/startdemotionvote` can be applied."
			% Record["question"], ephemeral=True)
		return
	if not poll_store.Is_Closed(Record):
		Closes = discord.utils.format_dt(poll_store.As_Aware(Record["closes_at"]), "R")
		await interaction.followup.send(
			"**% s** is still open, closing %s. Close it with `/pollend poll_id:% s` first so the "
			"result being acted on is final." % (Record["question"], Closes, poll_id),
			ephemeral=True)
		return
	# A rank vote is Yes/No, so it passed when the first answer won outright
	Tally, Voter_Count = poll_store.Tally(Record)
	Affirmative = Record["answers"][0]
	Won = poll_format.Winners(Tally)
	Passed = (len(Won) == 1 and Won[0] == Affirmative)
	if Record.get("applied_at") and not force:
		await interaction.followup.send(
			"%s\n\nThis vote was already applied by %s. Pass `force:True` to run it again."
			% (poll_view.Reference(Record), Record.get("applied_name") or "someone"),
			ephemeral=True)
		return
	if not Passed and not force:
		if not Won:
			Reason_Text = "nobody voted"
		elif len(Won) > 1:
			Reason_Text = "it tied - " + ", ".join("**%s**" % W for W in Won)
		else:
			Reason_Text = "**%s** won" % Won[0]
		await interaction.followup.send(
			"%s\n\n**%s** did not pass: %s.\n%s\n\nPass `force:True` to apply it anyway."
			% (poll_view.Reference(Record), Affirmative, Reason_Text, poll_format.Outcome(Tally)),
			ephemeral=True)
		return
	Guild = interaction.client.get_guild(int(DISCORD_GUILD)) or interaction.guild
	# The rank the vote was about. role_id/role_name are resolved fresh from
	# promotion_rank_id_new by poll_store._Hydrate. Fall back to matching by
	# name in case the mapped role was deleted and remade under a new id.
	Role = Guild.get_role(Record.get("role_id") or 0)
	if Role is None and Record.get("role_name"):
		Role = rank_ladder.Find_Role_By_Name(Guild, Record["role_name"])
	if Role is None:
		await interaction.followup.send(
			"The rank this vote was about (**%s**) no longer exists in this server, so there is "
			"nothing to give." % (Record.get("role_name") or "?"), ephemeral=True)
		return
	# The rank they held when the vote opened, removed as part of the change
	Old_Role = None
	if poll_store.Is_Rank_Vote(Record):
		Old_Role = Guild.get_role(Record.get("from_role_id") or 0)
		if Old_Role is None and Record.get("from_role_name"):
			Old_Role = rank_ladder.Find_Role_By_Name(Guild, Record["from_role_name"])
	Blocker = poll_members.Role_Blocker(Guild, Role, Old_Role)
	if Blocker:
		await interaction.followup.send(Blocker, ephemeral=True)
		return
	Subject = await poll_members.Resolve_Member(Guild, Subject_Id)
	if Subject is None:
		await interaction.followup.send(
			"**%s** is no longer in the server." % (Record.get("subject_name") or "That member"),
			ephemeral=True)
		return
	Header = "%s\n%s (%d vote(s), %d member(s) voted)" % (
		poll_view.Reference(Record), poll_format.Outcome(Tally),
		sum(c for _, c in Tally), Voter_Count)
	if not Passed:
		Header += "\n_Forced: the vote did not pass._"
	if Record.get("author_name"):
		Header += "\n_Vote started by %s._" % Record["author_name"]
	# Show each rank with its icon, the same way the vote itself did. Looked up
	# live against the guild now Role/Old_Role are resolved, rather than a
	# stored value - see poll_store.py's module docstring.
	New_Label = rank_ladder.With_Icon(rank_ladder.Icon(Guild, Role.name), Role.name)
	Old_Label = (rank_ladder.With_Icon(rank_ladder.Icon(Guild, Old_Role.name), Old_Role.name)
				 if Old_Role else "")
	Adding = Role not in Subject.roles
	Removing = Old_Role is not None and Old_Role in Subject.roles
	if not Adding and not Removing:
		await interaction.followup.send(
			"%s\n\n**%s** already holds **%s**%s. Nothing to do."
			% (Header, Subject.display_name, New_Label,
			   " and no longer holds the old rank" if Old_Role else ""), ephemeral=True)
		return
	Plan = []
	if Adding:
		Plan.append("give **%s**" % New_Label)
	if Removing:
		Plan.append("remove **%s**" % Old_Label)
	Plan_Text = " and ".join(Plan)
	if not apply:
		await interaction.followup.send(
			"%s\n\nDRY RUN, nothing changed.\nWould %s for **%s**.\n\n"
			"Re-run with `apply:True` to make the change."
			% (Header, Plan_Text, Subject.display_name), ephemeral=True)
		return
	Audit_Reason = "Poll %s passed" % poll_store.Poll_Key_Encode(Record["poll_id"])
	Problems = []
	# Add first: if the removal then fails they are left holding the new rank
	# rather than none at all.
	if Adding:
		try:
			await Subject.add_roles(Role, reason=Audit_Reason)
		except discord.HTTPException as Error:
			Problems.append("could not give **%s**: %s" % (Role.name, Error))
	if Removing:
		try:
			await Subject.remove_roles(Old_Role, reason=Audit_Reason)
		except discord.HTTPException as Error:
			Problems.append("could not remove **%s**: %s" % (Old_Role.name, Error))
	if Problems:
		await interaction.followup.send(
			"%s\n\nPartly applied for **%s**:\n%s"
			% (Header, Subject.display_name, "\n".join("- " + P for P in Problems)),
			ephemeral=True)
		return
	# Noted so it drops out of the grant list rather than lingering as a choice
	poll_store.Mark_Applied(SQL_Connection, SQL_Cursor, Record["poll_id"], interaction.user.id)
	await interaction.followup.send(
		"%s\n\nApplied for **%s**: %s." % (Header, Subject.display_name, Plan_Text), ephemeral=True)

# Polls subcommand group; appears in Discord as "/points <subcommand>"
Polls_Group = app_commands.Group(name="poll", description="Manage polls", guild_ids=[int(DISCORD_GUILD)])

#Command for creating a poll
@Polls_Group.command(name="create", description="Create a poll in a specific channel")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(channel="The channel to post the poll into", question="The poll question", answers="Options separated by | for example: Yes | No | Abstain", hours="How long voting stays open, 1 to 768 hours (default 24)", multiple="Let each member pick more than one option (default False)")
async def create(interaction: discord.Interaction, channel: discord.TextChannel, question: str, answers: str, hours: int = 24, multiple: bool = False):
	await Create(interaction, channel, question, answers, hours, multiple)    

#Command for ending a poll before time is up
@Polls_Group.command(name="end", description="Close a poll now and publish the counts")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(poll_id="The poll's ID, shown at the bottom of the poll message")
async def end(interaction: discord.Interaction, poll_id: str):
	await End(interaction, poll_id)
@end.autocomplete("poll_id")
async def end_id_autocomplete(interaction: discord.Interaction, current: str):
	return [app_commands.Choice(name=Display, value=Key)
		for Key, Display in poll_store.Open_Choices(SQL_Cursor, current)][:25]

#Command for counting the results of a poll once voting has closed
@Polls_Group.command(name="results", description="Show the results of a poll")
@app_commands.describe(poll_id="The poll's ID, shown at the bottom of the poll message")
async def results(interaction: discord.Interaction, poll_id: str):
	await Results(interaction, poll_id)
@results.autocomplete("poll_id")
async def results_id_autocomplete(interaction: discord.Interaction, current: str):
	return [app_commands.Choice(name=Display, value=Key)
			for Key, Display in poll_store.Recent_Choices(SQL_Cursor, current)][:25]

#Command for showing detailed results of a poll once voting has closed
@Polls_Group.command(name="results_detailed",description="Show a poll's results broken down by member")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(poll_id="The poll's ID, shown at the bottom of the poll message", force="Show the breakdown before voting has closed")
async def results_detailed(interaction: discord.Interaction, poll_id: str, force: bool = False):
	Results_Detailed(interaction, poll_id, force)
@results_detailed.autocomplete("poll_id")
async def results_detailed_id_autocomplete(interaction: discord.Interaction, current: str):
	return [app_commands.Choice(name=Display, value=Key)
			for Key, Display in poll_store.Recent_Choices(SQL_Cursor, current)][:25]

#Command for granting a poll
@Polls_Group.command(name="grant", description="Apply a closed rank vote to the member it was about")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(poll_id="The vote's ID, shown at the bottom of the poll message", apply="Actually make the change. Leave off for a dry run (default off)", force="Apply even though the vote did not pass (default off)")
async def grant(interaction: discord.Interaction, poll_id: str, apply: bool = False, force: bool = False):
	await Grant(interaction, poll_id, apply, force)
@grant.autocomplete("poll_id")
async def poll_grant_id_autocomplete(interaction: discord.Interaction, current: str):
	# Closed, about somebody, not already applied, newest first. Typing searches
	# the whole history, so an older vote is still reachable.
	return [app_commands.Choice(name=Display, value=Key)
			for Key, Display in poll_store.Grantable_Choices(SQL_Cursor, current)][:25]

#Add command list for the points management
tree.add_command(Polls_Group)