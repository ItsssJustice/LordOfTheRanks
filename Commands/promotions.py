PROMOTION_CHANNEL = 989662723518382089
PROMOTION_CHANNEL = 989662725871394850
PROMOTION_VOTE_TIME = 48

# Helpers here are prefixed Promotion_ because every Commands/ file shares one
# exec namespace: polls.py defines its own End/Grant, and whichever file ran
# last would otherwise win both.
#
# AUTOMATIC GRANTS: when a rank vote closes (on its deadline via
# poll_setup.Close_Expired_Polls, or early via /rank_vote end or /poll end),
# Promotion_On_Poll_Closed applies it straight away if it passed and either
#   - it's a demotion (always automatic), or
#   - it's a promotion onto a rank with discord_promotion_ranks.automatic_promotion set,
# with the bot's own discord id as applied_id. Everything else waits for a
# level 2 moderator to run /rank_vote action.

#Moderator level needed to open/close rank votes, and to apply one by hand
PROMOTION_VOTE_MODERATOR_LEVEL = 1
PROMOTION_GRANT_MODERATOR_LEVEL = 2

#Stop a command unless the caller is a moderator of at least the given level
async def Promotion_Moderator_Check(interaction, Level):
	if not sql_account_discord.Discord_Moderator_Command_Permitted(SQL_Cursor, interaction.user.id, Level):
		await bot_config.Command_Permissions_Issue(interaction)
		return False
	return True

async def Promotion_Channel_Get(interaction, channel_id):
	"""The promotion channel, resolved live rather than trusted from cache -
	or None if it can't be found, having already told the user why."""
	Channel = interaction.client.get_channel(channel_id)
	if Channel is None:
		try:
			Channel = await interaction.client.fetch_channel(channel_id)
		except discord.HTTPException:
			Channel = None
	if Channel is None:
		await interaction.response.send_message(
			"I can't find the promotion channel (id %s). Check PROMOTION_CHANNEL." % channel_id,
			ephemeral=True)
	return Channel

def Promotion_Answers(Current_Label, Target_Label):
	"""The two answers, each naming the rank it results in.
	Order matters: the first answer is the affirmative, and granting reads it
	as "the vote passed" when it wins.
	"""
	return ["Yes - %s" % Target_Label, "No - stay %s" % Current_Label]

#Phrase a promotion_rules result code for the caller
def Promotion_Rule_Text(Code, Details, Subject, Target):
	if Code == "self_vote":
		return "You can't open a promotion or demotion vote on yourself."
	elif Code == "vote_in_progress":
		Open_Vote = Details["poll"]
		Kind = "demotion" if Open_Vote["poll_type"] == sql_poll.POLL_TYPE_DEMOTION else "promotion"
		Key = poll_store.Poll_Key_Encode(Open_Vote["poll_id"])
		return ("There's already a %s vote open on **%s** (`%s`), closing %s. Only one rank vote can run "
				"on a member at a time - wait for it to close, or close it early with `/rank_vote end poll_id:%s`."
				% (Kind, Subject.display_name, Key,
				   discord.utils.format_dt(poll_store.As_Aware(Open_Vote["closes_at"]), "R"), Key))
	elif Code == "caller_no_rank":
		return "You don't hold a rank on the ladder, so you can't open rank votes."
	elif Code == "rank_too_low":
		return ("You can only open promotion votes onto ranks equal to or below your own. "
				"**%s** is above your rank of **%s**." % (Target.name, Details["caller_role"].name))
	elif Code == "equal_rank_wait":
		return ("**%s** is your own rank. You can promote members onto it %d day(s) after you were "
				"promoted to it, which is %s." % (Target.name, Details["wait_days"],
				discord.utils.format_dt(Details["until"], "R")))
	elif Code == "rank_sync_pending":
		return ("**%s** is your own rank, and your rank has changed since the last member sync. "
				"Promoting onto your own rank has a %d day wait from when you got it, counted once the sync "
				"records the change." % (Target.name, Details.get("wait_days", 0)))
	elif Code == "config_missing":
		return ("**%s** is your own rank, but `%s` is missing from bot_config, so I can't check the wait. "
				"Ask an admin to add it." % (Target.name, promotion_rules.EQUAL_RANK_DELAY_CONFIG))
	elif Code == "subject_not_below":
		return ("You can only open demotion votes on members ranked below you. **%s** is not below your "
				"rank of **%s**." % (Subject.display_name, Details["caller_role"].name))
	else:
		return "You can't open this rank vote (%s)." % Code

async def Promotion_Start(SQL_Connection, SQL_Cursor, client, interaction, Direction, member, channel, hours, Role=None):
	Word = "Promote" if Direction == rank_ladder.PROMOTION else "Demote"
	Poll_Type = sql_poll.POLL_TYPE_PROMOTION if Direction == rank_ladder.PROMOTION else sql_poll.POLL_TYPE_DEMOTION

	if hours < 1 or hours > 768:
		await interaction.response.send_message("Duration must be 1 to 768 hours.", ephemeral=True)
		return
	if member.bot:
		await interaction.response.send_message("Bots don't hold clan ranks.", ephemeral=True)
		return
	Guild = interaction.guild
	# Their rank now. Reading this does not depend on what channels they can see;
	# roles belong to guild membership.
	Current = rank_ladder.Current_Rank(SQL_Cursor, member)
	if Current is None:
		await interaction.response.send_message(
			"**%s** doesn't hold any rank on the ladder, so there is nothing to %s from.\n"
			"Give them a starting rank first." % (member.display_name, Word.lower()),
			ephemeral=True)
		return
	# One step along the ladder, unless a specific rank was named
	if Role is not None:
		Target = Role
		Problem = rank_ladder.Validate_Target(SQL_Cursor, Current, Target, Direction)
	else:
		Target, Problem = rank_ladder.Step(SQL_Cursor, Guild, Current, Direction)
	if Problem:
		await interaction.response.send_message(Problem, ephemeral=True)
		return
	# Who may open this vote: never on yourself, never while another rank vote on
	# them is open, promotions no higher than your own rank (with a delay for your
	# own), demotions only of members below you. Nothing between this check and
	# poll_store.Create below awaits, so two moderators can't both slip past it.
	Rule_Code, Rule_Details = promotion_rules.Rank_Vote_Start_Permitted(SQL_Cursor, interaction.user, member, Current, Target, Direction)
	if Rule_Code is not None:
		await interaction.response.send_message(Promotion_Rule_Text(Rule_Code, Rule_Details, member, Target), ephemeral=True)
		return
	# Each rank has a matching emote; show it so the vote reads at a glance.
	Current_Icon = rank_ladder.Icon(Guild, Current.name)
	Target_Icon = rank_ladder.Icon(Guild, Target.name)
	Question = "%s %s from %s to %s?" % (
		Word, member.display_name,
		rank_ladder.With_Icon(Current_Icon, Current.name),
		rank_ladder.With_Icon(Target_Icon, Target.name))
	Answer_List = Promotion_Answers(rank_ladder.With_Icon(Current_Icon, Current.name), rank_ladder.With_Icon(Target_Icon, Target.name))
	Current_Rank_Id = rank_ladder.Rank_Id_For(SQL_Cursor, Current.id)
	Target_Rank_Id = rank_ladder.Rank_Id_For(SQL_Cursor, Target.id)
	Record = poll_store.Create(
		SQL_Connection, SQL_Cursor, channel.id, interaction.user.id, Question, Answer_List,
		False, hours, Poll_Type=Poll_Type, Subject_Id=member.id,
		Promotion_Rank_Id_Current=Current_Rank_Id, Promotion_Rank_Id_New=Target_Rank_Id)
	try:
		Message = await channel.send(
			embed=poll_view.Build_Embed(Record),
			view=poll_view.Poll_Buttons(SQL_Connection, SQL_Cursor, Record["poll_id"], Answer_List))
	except discord.Forbidden:
		await interaction.response.send_message(
			"I'm missing permissions in %s. I need 'View Channel' and 'Send Messages' there."
			% channel.mention, ephemeral=True)
		return
	poll_store.Attach_Message(SQL_Connection, SQL_Cursor, Record["poll_id"], Message.id)
	Kind_Label = "Promotion" if Direction == rank_ladder.PROMOTION else "Demotion"
	# The vote can still run, but say now if the bot won't be able to apply it
	Blocker = poll_members.Role_Blocker(Guild, Target, Current)
	Blocker_Note = ("\n\n**Heads up:** I won't be able to apply this if it passes. %s" % Blocker) if Blocker else ""
	Chosen_Note = " (chosen, not the next rank on the ladder)" if Role is not None else ""
	Key = poll_store.Poll_Key_Encode(Record["poll_id"])
	if Promotion_Is_Automatic(SQL_Cursor, Record):
		Apply_Note = "If it passes, it's applied automatically when voting closes."
	else:
		Apply_Note = "Once it closes, a level %d moderator applies it with `/rank_vote action poll_id:%s`" % (PROMOTION_GRANT_MODERATOR_LEVEL, Key)
	await interaction.response.send_message(
		"%s\n%s vote posted in %s.\n**%s**: %s  ->  %s%s\n"
		"Close it early with `/rank_vote end poll_id:%s`. %s\n%s"
		% (poll_view.Reference(Record), Kind_Label, channel.mention,
		   member.display_name,
		   rank_ladder.With_Icon(Current_Icon, Current.name),
		   rank_ladder.With_Icon(Target_Icon, Target.name),
		   Chosen_Note, Key, Apply_Note, Message.jump_url) + Blocker_Note,
		ephemeral=True)

# ---------------------------------------------------------------------------
# Granting: applying a closed rank vote to the member it was about
# ---------------------------------------------------------------------------
#
# Promotion_Grant_Apply does the work and returns a Result dict whose "code" says
# what happened; the callers phrase it (Promotion_Grant_Text for /rank_vote
# action, Promotion_Auto_Grant_Text for automatic grants).
#   "not_rank_vote"    a generic poll, so nobody to apply it to
#   "still_open"       voting hasn't closed yet
#   "already_applied"  skipped unless Force
#   "not_passed"       skipped unless Force
#   "role_missing"     the target rank's role no longer exists in the server
#   "blocked"          the bot can't manage one of the roles - Result["blocker"]
#   "subject_missing"  the member has left the server
#   "nothing_to_do"    they already hold the new rank and not the old one
#   "dry_run"          would change something, but Apply_Changes was False
#   "partial"          a role change failed - Result["problems"]
#   "applied"          done, and marked applied

def Promotion_Is_Automatic(SQL_Cursor, Record):
	"""Whether this rank vote is applied automatically once it passes."""
	if Record.get("poll_type") == sql_poll.POLL_TYPE_DEMOTION:
		return True
	if Record.get("poll_type") == sql_poll.POLL_TYPE_PROMOTION:
		return bool(sql_promotion.Rank_Automatic_Promotion_Get(SQL_Cursor, Record.get("promotion_rank_id_new")))
	return False

def Promotion_Grant_Result(Code, Record, **Extra):
	Result = {"code": Code, "record": Record}
	Result.update(Extra)
	return Result

async def Promotion_Grant_Apply(SQL_Connection, SQL_Cursor, Guild, Record, Applied_Id, Apply_Changes=True, Force=False):
	if not Record.get("subject_id") or not poll_store.Is_Rank_Vote(Record):
		return Promotion_Grant_Result("not_rank_vote", Record)
	if not poll_store.Is_Closed(Record):
		return Promotion_Grant_Result("still_open", Record)
	# A rank vote is Yes/No, so it passed when the first answer won outright
	Tally, Voter_Count = poll_store.Tally(Record)
	Affirmative = Record["answers"][0]
	Won = poll_format.Winners(Tally)
	Passed = (len(Won) == 1 and Won[0] == Affirmative)
	Base = {"tally": Tally, "voter_count": Voter_Count, "won": Won, "affirmative": Affirmative, "passed": Passed}
	if Record.get("applied_at") and not Force:
		return Promotion_Grant_Result("already_applied", Record, **Base)
	if not Passed and not Force:
		return Promotion_Grant_Result("not_passed", Record, **Base)
	# The rank the vote was about, resolved fresh from promotion_rank_id_new by
	# poll_store._Hydrate. Fall back to the name in case the role was remade.
	Role = Guild.get_role(Record.get("role_id") or 0)
	if Role is None and Record.get("role_name"):
		Role = rank_ladder.Find_Role_By_Name(Guild, Record["role_name"])
	if Role is None:
		return Promotion_Grant_Result("role_missing", Record, **Base)
	# The rank they held when the vote opened, removed as part of the change
	Old_Role = Guild.get_role(Record.get("from_role_id") or 0)
	if Old_Role is None and Record.get("from_role_name"):
		Old_Role = rank_ladder.Find_Role_By_Name(Guild, Record["from_role_name"])
	Blocker = poll_members.Role_Blocker(Guild, Role, Old_Role)
	if Blocker:
		return Promotion_Grant_Result("blocked", Record, blocker=Blocker, **Base)
	Subject = await poll_members.Resolve_Member(Guild, Record["subject_id"])
	if Subject is None:
		return Promotion_Grant_Result("subject_missing", Record, **Base)
	# Icons looked up live against the guild, see poll_store.py's module docstring
	New_Label = rank_ladder.With_Icon(rank_ladder.Icon(Guild, Role.name), Role.name)
	Old_Label = rank_ladder.With_Icon(rank_ladder.Icon(Guild, Old_Role.name), Old_Role.name) if Old_Role else ""
	Adding = Role not in Subject.roles
	Removing = Old_Role is not None and Old_Role in Subject.roles
	Base.update({"subject": Subject, "role": Role, "old_role": Old_Role, "new_label": New_Label, "old_label": Old_Label})
	if not Adding and not Removing:
		# Already in the state the vote asked for, so it's settled - marked applied
		# so it drops out of the grant lists
		if Apply_Changes:
			Record = poll_store.Mark_Applied(SQL_Connection, SQL_Cursor, Record["poll_id"], Applied_Id)
		return Promotion_Grant_Result("nothing_to_do", Record, **Base)
	Plan = []
	if Adding:
		Plan.append("give **%s**" % New_Label)
	if Removing:
		Plan.append("remove **%s**" % Old_Label)
	Base["plan_text"] = " and ".join(Plan)
	if not Apply_Changes:
		return Promotion_Grant_Result("dry_run", Record, **Base)
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
		return Promotion_Grant_Result("partial", Record, problems=Problems, **Base)
	# Noted so it drops out of the grant list rather than lingering as a choice
	Record = poll_store.Mark_Applied(SQL_Connection, SQL_Cursor, Record["poll_id"], Applied_Id)
	return Promotion_Grant_Result("applied", Record, **Base)

def Promotion_Subject_Name(Result):
	Subject = Result.get("subject")
	if Subject is not None:
		return Subject.display_name
	return Result["record"].get("subject_name") or "That member"

#The reply for a moderator's manual grant
def Promotion_Grant_Text(Result):
	Code = Result["code"]
	Record = Result["record"]
	Key = poll_store.Poll_Key_Encode(Record["poll_id"])
	Reference = poll_view.Reference(Record)
	if Code == "not_rank_vote":
		return ("**%s** is a generic poll, so there is nobody to apply it to.\n"
				"Only votes started with `/rank_vote promotion` or `/rank_vote demotion` can be applied."
				% Record["question"])
	elif Code == "still_open":
		Closes = discord.utils.format_dt(poll_store.As_Aware(Record["closes_at"]), "R")
		return ("**%s** is still open, closing %s. Close it with `/rank_vote end poll_id:%s` first so the "
				"result being acted on is final." % (Record["question"], Closes, Key))
	elif Code == "already_applied":
		return ("%s\n\nThis vote was already applied by %s."
				% (Reference, Record.get("applied_name") or "someone"))
	elif Code == "not_passed":
		Won = Result["won"]
		if not Won:
			Reason_Text = "nobody voted"
		elif len(Won) > 1:
			Reason_Text = "it tied - " + ", ".join("**%s**" % W for W in Won)
		else:
			Reason_Text = "**%s** won" % Won[0]
		return ("%s\n\n**%s** did not pass: %s.\n%s"
				% (Reference, Result["affirmative"], Reason_Text, poll_format.Outcome(Result["tally"])))
	elif Code == "role_missing":
		return ("The rank this vote was about (**%s**) no longer exists in this server, so there is "
				"nothing to give." % (Record.get("role_name") or "?"))
	elif Code == "blocked":
		return Result["blocker"]
	elif Code == "subject_missing":
		return "**%s** is no longer in the server." % Promotion_Subject_Name(Result)
	Tally = Result["tally"]
	Header = "%s\n%s (%d vote(s), %d member(s) voted)" % (
		Reference, poll_format.Outcome(Tally), sum(c for _, c in Tally), Result["voter_count"])
	if not Result["passed"]:
		Header += "\n_Forced: the vote did not pass._"
	if Record.get("author_name"):
		Header += "\n_Vote started by %s._" % Record["author_name"]
	if Code == "nothing_to_do":
		return ("%s\n\n**%s** already holds **%s**%s. Nothing to do, so it's been marked as applied."
				% (Header, Promotion_Subject_Name(Result), Result["new_label"],
				   " and no longer holds the old rank" if Result["old_role"] else ""))
	elif Code == "dry_run":
		return ("%s\n\nDRY RUN, nothing changed.\nWould %s for **%s**."
				% (Header, Result["plan_text"], Promotion_Subject_Name(Result)))
	elif Code == "partial":
		return ("%s\n\nPartly applied for **%s**:\n%s"
				% (Header, Promotion_Subject_Name(Result), "\n".join("- " + P for P in Result["problems"])))
	else:
		return "%s\n\nApplied for **%s**: %s." % (Header, Promotion_Subject_Name(Result), Result["plan_text"])

#One line on how an automatic grant went, for the poll's channel and the /end reply
def Promotion_Auto_Grant_Text(Result):
	Code = Result["code"]
	Record = Result["record"]
	Key = poll_store.Poll_Key_Encode(Record["poll_id"])
	Kind = "demotion" if Record.get("poll_type") == sql_poll.POLL_TYPE_DEMOTION else "promotion"
	Name = Promotion_Subject_Name(Result)
	if Code == "applied":
		return "Automatic %s `%s`: **%s** is now **%s**." % (Kind, Key, Name, Result["new_label"])
	elif Code == "nothing_to_do":
		return "Automatic %s `%s`: **%s** already holds **%s**, nothing to change." % (Kind, Key, Name, Result["new_label"])
	elif Code == "not_passed":
		return "Automatic %s `%s`: the vote did not pass, so nothing was applied." % (Kind, Key)
	elif Code == "already_applied":
		return "Automatic %s `%s`: already applied." % (Kind, Key)
	elif Code == "partial":
		Reason = "; ".join(Result["problems"])
	elif Code == "blocked":
		Reason = Result["blocker"]
	elif Code == "subject_missing":
		Reason = "they are no longer in the server"
	elif Code == "role_missing":
		Reason = "the rank **%s** no longer exists in this server" % (Record.get("role_name") or "?")
	else:
		Reason = Code
	return ("Automatic %s `%s` for **%s** could not be applied: %s\n"
			"A level %d moderator can apply it with `/rank_vote action poll_id:%s`."
			% (Kind, Key, Name, Reason, PROMOTION_GRANT_MODERATOR_LEVEL, Key))

async def Promotion_On_Poll_Closed(client, Guild, Record):
	"""Called whenever a poll closes. Applies a passed demotion, or a passed
	promotion onto an automatic rank, and posts the outcome in the poll's
	channel. Returns the grant Result, or None when this poll isn't one to
	grant automatically. poll_setup.Close_Expired_Polls receives this as its
	On_Poll_Closed callback from LordOfTheRanks.py."""
	if Record is None or Guild is None:
		return None
	# Re-read rather than trust the caller's copy: an early /end and the deadline
	# loop can both reach here for the same poll, and the second must see the
	# first one's applied flag.
	Record = poll_store.Find_By_Id(SQL_Cursor, Record["poll_id"])
	if Record is None or Record.get("applied"):
		return None
	if not Promotion_Is_Automatic(SQL_Cursor, Record):
		return None
	Result = await Promotion_Grant_Apply(SQL_Connection, SQL_Cursor, Guild, Record, client.user.id, True, False)
	print("Promotion : poll %s automatic grant -> %s" % (poll_store.Poll_Key_Encode(Record["poll_id"]), Result["code"]))
	# A vote that didn't pass already says so on the poll itself
	if Result["code"] not in ("not_passed", "already_applied"):
		await bot_config.Notify_Channel(client, Record.get("channel_id"), Promotion_Auto_Grant_Text(Result))
	return Result

async def Promotion_End(interaction: discord.Interaction, poll_id: str):
	Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
	if Record is None:
		await interaction.response.send_message("No poll with ID '%s'." % poll_id, ephemeral=True)
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
	Guild = interaction.client.get_guild(int(DISCORD_GUILD)) or interaction.guild
	Auto_Result = await Promotion_On_Poll_Closed(interaction.client, Guild, Record)
	if Auto_Result is not None:
		Lines.append("")
		Lines.append(Promotion_Auto_Grant_Text(Auto_Result))
	await interaction.followup.send("\n".join(Lines), ephemeral=True)

async def Promotion_Grant(interaction: discord.Interaction, poll_id: str, apply: bool = True, force: bool = False):
	Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
	if Record is None:
		await interaction.response.send_message("No poll with ID '%s'." % poll_id, ephemeral=True)
		return
	# Applying a promotion or demotion vote: moderators of level 2 and above only
	if poll_store.Is_Rank_Vote(Record) and not await Promotion_Moderator_Check(interaction, PROMOTION_GRANT_MODERATOR_LEVEL):
		return
	await interaction.response.defer(ephemeral=True)
	Guild = interaction.client.get_guild(int(DISCORD_GUILD)) or interaction.guild
	Result = await Promotion_Grant_Apply(SQL_Connection, SQL_Cursor, Guild, Record, interaction.user.id, apply, force)
	await interaction.followup.send(Promotion_Grant_Text(Result), ephemeral=True)

# Rank vote subcommand group; appears in Discord as "/rank_vote <subcommand>"
Promotions_Group = app_commands.Group(name="rank_vote", description="Manage promotions and demotions", guild_ids=[int(DISCORD_GUILD)])

#Command for creating a promotion vote
@Promotions_Group.command(name="promotion", description="Open a vote on promoting a member one rank")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(member="The member being voted on", role="Which rank to promote to. Leave empty for the next one on the ladder")
async def start_promotion_vote(interaction: discord.Interaction, member: discord.Member, role: discord.Role = None):
	if not await Promotion_Moderator_Check(interaction, PROMOTION_VOTE_MODERATOR_LEVEL):
		return
	Channel = await Promotion_Channel_Get(interaction, PROMOTION_CHANNEL)
	if Channel is None:
		return
	await Promotion_Start(SQL_Connection, SQL_Cursor, interaction.client, interaction, rank_ladder.PROMOTION, member, Channel, PROMOTION_VOTE_TIME, Role=role)

#Command for creating a demotion vote
@Promotions_Group.command(name="demotion", description="Open a vote on demoting a member one rank")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(member="The member being voted on", role="Which rank to demote to. Leave empty for the next one on the ladder")
async def start_demotion_vote(interaction: discord.Interaction, member: discord.Member, role: discord.Role = None):
	if not await Promotion_Moderator_Check(interaction, PROMOTION_VOTE_MODERATOR_LEVEL):
		return
	Channel = await Promotion_Channel_Get(interaction, PROMOTION_CHANNEL)
	if Channel is None:
		return
	await Promotion_Start(SQL_Connection, SQL_Cursor, interaction.client, interaction, rank_ladder.DEMOTION, member, Channel, PROMOTION_VOTE_TIME, Role=role)

#Command for ending a vote before time is up
@Promotions_Group.command(name="end", description="Close a vote now and publish the counts")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(poll_id="The poll's ID, shown at the bottom of the poll message")
async def end(interaction: discord.Interaction, poll_id: str):
	if not await Promotion_Moderator_Check(interaction, PROMOTION_VOTE_MODERATOR_LEVEL):
		return
	await Promotion_End(interaction, poll_id)
@end.autocomplete("poll_id")
async def end_id_autocomplete(interaction: discord.Interaction, current: str):
	return [app_commands.Choice(name=Display, value=Key)
		for Key, Display in poll_store.Open_Choices(SQL_Cursor, current)][:25]

#Command for granting a rank vote by hand (promotions onto non-automatic ranks, or a failed automatic grant)
@Promotions_Group.command(name="action", description="Apply a closed rank vote to the member it was about")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(poll_id="The vote's ID, shown at the bottom of the poll message")
async def grant(interaction: discord.Interaction, poll_id: str):
	if not await Promotion_Moderator_Check(interaction, PROMOTION_VOTE_MODERATOR_LEVEL):
		return
	await Promotion_Grant(interaction, poll_id, True, False)
@grant.autocomplete("poll_id")
async def grant_id_autocomplete(interaction: discord.Interaction, current: str):
	# Closed, about somebody, not already applied, newest first. Typing searches
	# the whole history, so an older vote is still reachable.
	return [app_commands.Choice(name=Display, value=Key)
			for Key, Display in poll_store.Grantable_Choices(SQL_Cursor, current)][:25]

#Add command list for the rank vote management
tree.add_command(Promotions_Group)
