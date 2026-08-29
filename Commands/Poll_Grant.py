# /pollgrant  --  apply the result of a rank vote to the member it was about.
#
# Everything it needs is already on the vote: who it was about, which rank was
# proposed, and which rank they held when it opened. So it takes none of that as
# input. It reads the result, and if the vote passed it makes the change.
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
    label="The vote's nickname",
    apply="Actually make the change. Leave off for a dry run (default off)",
    force="Apply even though the vote did not pass (default off)"
)
async def poll_grant(
    interaction: discord.Interaction,
    label: str,
    apply: bool = False,
    force: bool = False
):
    Record = poll_store.Find(label)
    if Record is None:
        await interaction.response.send_message("No poll labelled '% s'." % label, ephemeral=True)
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
        Closes = discord.utils.format_dt(discord.utils.parse_time(Record["closes_at"]), "R")
        await interaction.followup.send(
            "**% s** is still open, closing %s. Close it with `/pollend label:% s` first so the "
            "result being acted on is final." % (Record["question"], Closes, Record["label"]),
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
            % (poll_view.Reference(Record), Record.get("applied_by") or "someone"),
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

    Guild = interaction.client.get_guild(Record["guild_id"]) or interaction.guild

    # The rank the vote was about. Fall back to the name in case the role was
    # deleted and remade, which gives it a new id.
    Role = Guild.get_role(Record.get("role_id") or 0)
    if Role is None and Record.get("role_name"):
        Role = rank_ladder.Find_Role(Guild, Record["role_name"])
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
            Old_Role = rank_ladder.Find_Role(Guild, Record["from_role_name"])

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
    if Record.get("started_by_name"):
        Header += "\n_Vote started by %s._" % Record["started_by_name"]

    # Show each rank with its icon, the same way the vote itself did
    New_Label = rank_ladder.With_Icon(Record.get("role_icon") or "", Role.name)
    Old_Label = (rank_ladder.With_Icon(Record.get("from_role_icon") or "", Old_Role.name)
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

    Audit_Reason = "Poll %s passed" % Record["label"]
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
    poll_store.Mark_Applied(Record["label"], interaction.user.display_name)

    await interaction.followup.send(
        "%s\n\nApplied for **%s**: %s." % (Header, Subject.display_name, Plan_Text), ephemeral=True)


@poll_grant.autocomplete("label")
async def poll_grant_label_autocomplete(interaction: discord.Interaction, current: str):
    # Closed, about somebody, not already applied, newest first. Typing searches
    # the whole history, so an older vote is still reachable.
    return [app_commands.Choice(name=L, value=L)
            for L in poll_store.Grantable_Labels(current)][:25]
