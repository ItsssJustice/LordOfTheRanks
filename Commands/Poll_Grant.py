# /pollgrant  --  give a role to everyone who voted for a particular answer.
#
# This is the "do something with the result" example: it pulls the voter list
# out of the poll as Member objects and acts on them. Same shape works for
# awarding points, writing to a sheet, or anything else.
#
# Two deliberate safety rails, because this hands out ranks:
#   * apply defaults to False -- you get a preview of who WOULD be changed
#   * the poll must be closed, unless you pass allow_open:True. Discord only
#     guarantees precise vote counts once a poll has finalised.

@tree.command(
    name="pollgrant",
    description="Give a role to everyone who voted for one answer",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="The poll's nickname",
    answer="Which answer, counting from 1",
    role="The role to hand out",
    apply="Actually assign the role. Leave off for a dry run (default off)",
    allow_open="Proceed even though the poll is still running (default off)"
)
async def poll_grant(
    interaction: discord.Interaction,
    label: str,
    answer: int,
    role: discord.Role,
    apply: bool = False,
    allow_open: bool = False
):
    Record = poll_store.Find(label)
    if Record is None:
        await interaction.response.send_message("No poll labelled '% s'." % label, ephemeral=True)
        return

    # Fetching every voter plus member lookups can take a while
    await interaction.response.defer(ephemeral=True)

    Data = await poll_data.Fetch(client, Record, With_Voters=True)
    if Data is None:
        await interaction.followup.send("That poll can't be found any more.", ephemeral=True)
        return

    if answer < 1 or answer > len(Data["answers"]):
        Listing = "\n".join("  %d - %s" % (i + 1, A["text"]) for i, A in enumerate(Data["answers"]))
        await interaction.followup.send("Answer must be 1-%d:\n%s" % (len(Data["answers"]), Listing),
                                        ephemeral=True)
        return

    if not Data["closed"] and not allow_open:
        await interaction.followup.send(
            "**% s** is still running, so Discord doesn't guarantee the counts are final yet.\n"
            "Close it with `/pollend label:% s` first, or re-run with `allow_open:True`."
            % (Data["question"], Record["label"]), ephemeral=True)
        return

    Blocker = poll_data.Role_Blocker(Data["guild"], role)
    if Blocker:
        await interaction.followup.send(Blocker, ephemeral=True)
        return

    Chosen = Data["answers"][answer - 1]

    Granted, Already, Gone, Failed = [], [], 0, []
    for User in Chosen["voters"]:
        Member = await poll_data.Resolve_Member(Data["guild"], User)
        if Member is None:
            Gone += 1
            continue
        if role in Member.roles:
            Already.append(Member)
            continue
        if not apply:
            Granted.append(Member)
            continue
        try:
            await Member.add_roles(role, reason="Voted '%s' in poll '%s'" % (Chosen["text"], Record["label"]))
            Granted.append(Member)
        except discord.Forbidden:
            Failed.append(Member)
        except discord.HTTPException:
            Failed.append(Member)

    Lines = ["%s **%s** -> voted **%s** (%d)" % (
        "Granted" if apply else "DRY RUN, nothing changed. Would grant",
        role.name, Chosen["text"], Chosen["count"])]
    Lines.append("")
    Lines.append("%s: %d%s" % ("Given the role" if apply else "Would receive it",
                               len(Granted),
                               (" - " + ", ".join(M.display_name for M in Granted[:20])) if Granted else ""))
    if Already:
        Lines.append("Already had it: %d" % len(Already))
    if Gone:
        Lines.append("No longer in the server: %d" % Gone)
    if Failed:
        Lines.append("Failed: %d - %s" % (len(Failed), ", ".join(M.display_name for M in Failed[:10])))
    if not apply and Granted:
        Lines.append("")
        Lines.append("Re-run with `apply:True` to actually assign it.")

    await interaction.followup.send("\n".join(Lines), ephemeral=True)


@poll_grant.autocomplete("label")
async def poll_grant_label_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=L, value=L)
            for L in poll_store.Labels() if current.lower() in L.lower()][:25]


# Answers are saved into Polls.json at creation time, so this autocompletes
# from local data instead of hitting the API on every keystroke.
@poll_grant.autocomplete("answer")
async def poll_grant_answer_autocomplete(interaction: discord.Interaction, current: str):
    Record = poll_store.Find(getattr(interaction.namespace, "label", "") or "")
    if not Record:
        return []
    return [app_commands.Choice(name="%d - %s" % (i + 1, Text), value=i + 1)
            for i, Text in enumerate(Record.get("answers", []))][:25]
