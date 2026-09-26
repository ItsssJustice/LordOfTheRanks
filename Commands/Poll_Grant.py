# /pollgrant  --  apply the result of a rank vote to the member it was about.
#
# Everything it needs is already on the vote: who it was about, which
# promotion rank was proposed, and which rank they held when it opened. So it
# takes none of that as input. It reads the result, and if the vote passed it
# makes the change.
#
# "Passed" means the first answer -- the affirmative -- is the outright winner.
# A loss, a tie or an empty vote all stop it, and force overrides that.
#
# For a promotion or demotion this is a rank CHANGE: the new rank is added and
# the old one removed, because ranks on the ladder are exclusive - nobody should
# end up holding both Sergeant and Cadet.
#
# It never touches the people who voted. Voting for an answer is an opinion about
# the subject, not a request for the role.
#
# The role to grant/remove is resolved from promotion_rank_id_new/current via
# discord_promotion_ranks -> discord_roles at the moment /pollgrant runs, not
# from an id frozen when the vote was opened - so if that mapping changes
# between opening the vote and granting it, this picks up the CURRENT mapping.
#
# Two rails, because this changes ranks:
#   * apply defaults to False, so you get a preview of exactly what would change
#   * the vote must be closed, so the result being acted on is the final one

@tree.command(
    name="pollgrant",
    description="Apply a closed rank vote to the member it was about",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    poll_id="The vote's ID, shown at the bottom of the poll message",
    apply="Actually make the change. Leave off for a dry run (default off)",
    force="Apply even though the vote did not pass (default off)"
)
async def poll_grant(
    interaction: discord.Interaction,
    poll_id: str,
    apply: bool = False,
    force: bool = False
):
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


@poll_grant.autocomplete("poll_id")
async def poll_grant_id_autocomplete(interaction: discord.Interaction, current: str):
    # Closed, about somebody, not already applied, newest first. Typing searches
    # the whole history, so an older vote is still reachable.
    return [app_commands.Choice(name=Display, value=Key)
            for Key, Display in poll_store.Grantable_Choices(SQL_Cursor, current)][:25]
