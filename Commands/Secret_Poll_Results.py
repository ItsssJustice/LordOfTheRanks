# /secretpollresults      -- counts only, and only once voting has closed
# /secretpolldetailed     -- who voted for what, restricted
#
# The whole reason this poll type exists is to stop people being swayed by how
# others have voted, so counts stay sealed while the ballot is open. Staff are
# not exempt: a staff member who could peek mid-vote could still leak or act on
# it, which reintroduces exactly the pressure this is meant to remove.

@tree.command(
    name="secretpollresults",
    description="Show the counts for a secret ballot (available once it closes)",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.describe(label="The ballot's nickname")
async def secret_poll_results(interaction: discord.Interaction, label: str):
    Record = secret_store.Find(label)
    if Record is None:
        Known = secret_store.Labels()
        await interaction.response.send_message(
            "No secret poll labelled '% s'. Known: % s" % (label, ", ".join(Known) if Known else "none yet"),
            ephemeral=True)
        return

    if not secret_store.Is_Closed(Record):
        Closes = discord.utils.format_dt(discord.utils.parse_time(Record["closes_at"]), "R")
        await interaction.response.send_message(
            "**% s** is still open, so the counts are sealed. It closes %s.\n"
            "Staff can end it early with `/secretpollend label:% s`."
            % (Record["question"], Closes, Record["label"]), ephemeral=True)
        return

    Tally, Ballots = secret_store.Tally(Record)
    Total = sum(c for _, c in Tally)
    Lines = ["**% s**" % Record["question"], "_Closed_ | %d ballot(s), %d vote(s)" % (Ballots, Total), ""]
    for Text, Count in Tally:
        Bar, Share = poll_format.Bar(Count, Total)
        Lines.append("`%-3d` %s  %s %.0f%%" % (Count, Text, Bar, Share))

    Top = max((c for _, c in Tally), default=0)
    Winners = [t for t, c in Tally if c == Top and Top > 0]
    Lines.append("")
    if not Winners:
        Lines.append("Closed with no votes cast.")
    elif len(Winners) == 1:
        Lines.append("Winner: **%s** (%d)" % (Winners[0], Top))
    else:
        Lines.append("Tied on %d: %s" % (Top, ", ".join("**%s**" % w for w in Winners)))

    await interaction.response.send_message("\n".join(Lines), ephemeral=True)


@tree.command(
    name="secretpolldetailed",
    description="Show who voted for what in a secret ballot (restricted)",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="The ballot's nickname",
    force="Reveal even though voting is still open. Do not do this casually."
)
async def secret_poll_detailed(interaction: discord.Interaction, label: str, force: bool = False):
    Record = secret_store.Find(label)
    if Record is None:
        await interaction.response.send_message("No secret poll labelled '% s'." % label, ephemeral=True)
        return

    if not secret_store.Is_Closed(Record) and not force:
        await interaction.response.send_message(
            "**% s** is still open. Revealing who voted while people are still voting defeats the "
            "point of a secret ballot.\nClose it with `/secretpollend label:% s`, or pass "
            "`force:True` if you genuinely need to look now."
            % (Record["question"], Record["label"]), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    Guild = client.get_guild(Record["guild_id"]) or interaction.guild
    Lines = ["**% s**" % Record["question"]]
    Lines.append("_% s_" % ("Closed" if secret_store.Is_Closed(Record) else "STILL OPEN - revealed early"))
    Lines.append("")

    for Text, User_Ids in secret_store.Voters_By_Answer(Record):
        Lines.append("**%s** - %d" % (Text, len(User_Ids)))
        if not User_Ids:
            Lines.append("  _nobody_")
        else:
            Names = []
            for User_Id in User_Ids:
                Member = Guild.get_member(User_Id) if Guild else None
                if Member is None:
                    try:
                        Member = await Guild.fetch_member(User_Id)
                    except Exception:
                        Member = None
                Names.append(Member.display_name if Member else "unknown (%d)" % User_Id)
            Lines.append("  " + ", ".join(Names))
        Lines.append("")

    Body = "\n".join(Lines)
    Chunks, Current = [], ""
    for Line in Body.split("\n"):
        if len(Current) + len(Line) + 1 > 1900:
            Chunks.append(Current); Current = ""
        Current += Line + "\n"
    Chunks.append(Current)
    for Chunk in Chunks:
        await interaction.followup.send(Chunk, ephemeral=True)


for _Command in (secret_poll_results, secret_poll_detailed):
    @_Command.autocomplete("label")
    async def _secret_label_ac(interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=L, value=L)
                for L in secret_store.Labels() if current.lower() in L.lower()][:25]
