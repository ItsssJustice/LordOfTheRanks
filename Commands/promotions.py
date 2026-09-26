PROMOTION_CHANNEL = 989662723518382089
PROMOTION_CHANNEL = 989662725871394850
PROMOTION_VOTE_TIME = 48

#from Functions import sql_poll, poll_store, poll_view, rank_ladder
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

def Answers(Current_Label, Target_Label):
    """The two answers, each naming the rank it results in.
    Order matters: the first answer is the affirmative, and /pollgrant reads it
    as "the vote passed" when it wins.
    """
    return ["Yes - %s" % Target_Label, "No - stay %s" % Current_Label]

async def Start(SQL_Connection, SQL_Cursor, client, interaction, Direction, member, channel, hours, Role=None):
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
    # Each rank has a matching emote; show it so the vote reads at a glance.
    Current_Icon = rank_ladder.Icon(Guild, Current.name)
    Target_Icon = rank_ladder.Icon(Guild, Target.name)
    Question = "%s %s from %s to %s?" % (
        Word, member.display_name,
        rank_ladder.With_Icon(Current_Icon, Current.name),
        rank_ladder.With_Icon(Target_Icon, Target.name))
    Answer_List = Answers(rank_ladder.With_Icon(Current_Icon, Current.name), rank_ladder.With_Icon(Target_Icon, Target.name))
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
    Chosen_Note = " (chosen, not the next rank on the ladder)" if Role is not None else ""
    Key = poll_store.Poll_Key_Encode(Record["poll_id"])
    await interaction.response.send_message(
        "%s\n%s vote posted in %s.\n**%s**: %s  ->  %s%s\n"
        "Close it with `/pollend poll_id:%s`, then apply it with `/pollgrant poll_id:%s`\n%s"
        % (poll_view.Reference(Record), Kind_Label, channel.mention,
           member.display_name,
           rank_ladder.With_Icon(Current_Icon, Current.name),
           rank_ladder.With_Icon(Target_Icon, Target.name),
           Chosen_Note, Key, Key, Message.jump_url),
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
Promotions_Group = app_commands.Group(name="rank_vote", description="Manage promotions and demotions", guild_ids=[int(DISCORD_GUILD)])

#Command for creating a promotion vote
@Promotions_Group.command(name="promotion", description="Open a vote on promoting a member one rank")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(member="The member being voted on", role="Which rank to promote to. Leave empty for the next one on the ladder")
async def start_promotion_vote(interaction: discord.Interaction, member: discord.Member, role: discord.Role = None):
    Channel = await Promotion_Channel_Get(interaction, PROMOTION_CHANNEL)
    if Channel is None:
        return
    await Start(SQL_Connection, SQL_Cursor, interaction.client, interaction, rank_ladder.PROMOTION, member, Channel, PROMOTION_VOTE_TIME, Role=role)
#Command for creating a demotion vote
@Promotions_Group.command(name="demotion", description="Open a vote on demoting a member one rank")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(member="The member being voted on", role="Which rank to demote to. Leave empty for the next one on the ladder")
async def start_demotion_vote(interaction: discord.Interaction, member: discord.Member, role: discord.Role = None):
    Channel = await Promotion_Channel_Get(interaction, PROMOTION_CHANNEL)
    if Channel is None:
        return
    await Start(SQL_Connection, SQL_Cursor, interaction.client, interaction, rank_ladder.DEMOTION, member, Channel, PROMOTION_VOTE_TIME, Role=role)

#Command for ending a vote before time is up
@Promotions_Group.command(name="end", description="Close a vote now and publish the counts")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(poll_id="The poll's ID, shown at the bottom of the poll message")
async def end(interaction: discord.Interaction, poll_id: str):
	await End(interaction, poll_id)
@end.autocomplete("poll_id")
async def end_id_autocomplete(interaction: discord.Interaction, current: str):
	return [app_commands.Choice(name=Display, value=Key)
		for Key, Display in poll_store.Open_Choices(SQL_Cursor, current)][:25]

#Command for granting a promotion
@Promotions_Group.command(name="action", description="Apply a closed rank vote to the member it was about")
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(poll_id="The vote's ID, shown at the bottom of the poll message")
async def grant(interaction: discord.Interaction, poll_id: str):
	await Grant(interaction, poll_id, True, False)
@grant.autocomplete("poll_id")
async def grant_id_autocomplete(interaction: discord.Interaction, current: str):
	# Closed, about somebody, not already applied, newest first. Typing searches
	# the whole history, so an older vote is still reachable.
	return [app_commands.Choice(name=Display, value=Key)
			for Key, Display in poll_store.Grantable_Choices(SQL_Cursor, current)][:25]

#Add command list for the points management
tree.add_command(Promotions_Group)