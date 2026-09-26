# /polldetailedresults  --  the counts broken down by who chose each answer.

@tree.command(
    name="polldetailedresults",
    description="Show a poll's results broken down by member",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    poll_id="The poll's ID, shown at the bottom of the poll message",
    force="Show the breakdown before voting has closed"
)
async def poll_detailed_results(interaction: discord.Interaction, poll_id: str, force: bool = False):
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


@poll_detailed_results.autocomplete("poll_id")
async def poll_detailed_results_id_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=Display, value=Key)
            for Key, Display in poll_store.Recent_Choices(SQL_Cursor, current)][:25]
