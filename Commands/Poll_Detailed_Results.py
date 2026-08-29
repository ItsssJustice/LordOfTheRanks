# /polldetailedresults  --  the counts broken down by who chose each answer.

@tree.command(
    name="polldetailedresults",
    description="Show a poll's results broken down by member",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="The poll's nickname",
    force="Show the breakdown before voting has closed"
)
async def poll_detailed_results(interaction: discord.Interaction, label: str, force: bool = False):
    Record = poll_store.Find(label)
    if Record is None:
        await interaction.response.send_message("No poll labelled '% s'." % label, ephemeral=True)
        return

    if not poll_store.Is_Closed(Record) and not force:
        Closes = discord.utils.format_dt(discord.utils.parse_time(Record["closes_at"]), "R")
        await interaction.response.send_message(
            "**% s** is still open, closing %s.\nClose it with `/pollend label:% s`, or pass "
            "`force:True` to see the breakdown now."
            % (Record["question"], Closes, Record["label"]), ephemeral=True)
        return

    # One member lookup per voter, so buy ourselves some time
    await interaction.response.defer(ephemeral=True)

    Guild = interaction.client.get_guild(Record["guild_id"]) or interaction.guild
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


@poll_detailed_results.autocomplete("label")
async def poll_detailed_label_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=L, value=L)
            for L in poll_store.Recent_Labels(current)][:25]
