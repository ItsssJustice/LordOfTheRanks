# /polldetailedresults  --  who voted for what.
#
# Split out from /pollresults on purpose: Discord lets you set per-command
# permissions, so this one can be locked to ranking staff while everyone keeps
# access to the plain counts.
#
# The default_permissions decorator below sets the DEFAULT gate (members who
# can Manage Roles). It is only a default -- the real control is
#   Server Settings > Integrations > [your bot] > Command Permissions
# where you can allow/deny per role or per member, and that overrides this.
#
# NOTE ON PRIVACY: gating this command does NOT make the poll secret. Discord's
# own client lets anyone click a native poll's vote count and see the voter
# list. This command is a convenience, not a confidentiality control.

@tree.command(
    name="polldetailedresults",
    description="Show who voted for what (restricted)",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="The nickname you gave the poll when you created it",
    public="Post the breakdown visibly in the channel instead of just to you (default off)"
)
async def poll_detailed_results(interaction: discord.Interaction, label: str, public: bool = False):
    Record = poll_store.Find(label)
    if Record is None:
        Known = poll_store.Labels()
        await interaction.response.send_message(
            "No poll labelled '% s'. Known polls: % s" % (label, ", ".join(Known) if Known else "none yet"),
            ephemeral=True)
        return

    # One API call per answer to page the voters, so buy ourselves some time
    await interaction.response.defer(ephemeral=not public)

    Data = await poll_data.Fetch(client, Record, With_Voters=True)
    if Data is None:
        await interaction.followup.send("That poll can't be found any more.", ephemeral=True)
        return

    Lines = ["**% s**" % Data["question"]]
    Lines.append("_% s_ | %d vote(s) total" % ("Closed" if Data["closed"] else "Still open", Data["total"]))
    if not Data["closed"]:
        Lines.append("_Counts aren't final until the poll closes._")
    Lines.append("")

    for Answer in Data["answers"]:
        Lines.append("**%s** - %d" % (Answer["text"], Answer["count"]))
        if Answer["voters"]:
            Names = []
            for User in Answer["voters"]:
                Member = await poll_data.Resolve_Member(Data["guild"], User)
                Names.append(Member.display_name if Member else "%s (left)" % User.name)
            Lines.append("  " + ", ".join(Names))
        else:
            Lines.append("  _nobody_")
        Lines.append("")

    Lines.append(Data["message"].jump_url)

    # A big clan poll can blow past discord's 2000 character message limit
    Body = "\n".join(Lines)
    Chunks, Current = [], ""
    for Line in Body.split("\n"):
        if len(Current) + len(Line) + 1 > 1900:
            Chunks.append(Current); Current = ""
        Current += Line + "\n"
    Chunks.append(Current)

    for i, Chunk in enumerate(Chunks):
        await interaction.followup.send(Chunk, ephemeral=not public)


@poll_detailed_results.autocomplete("label")
async def poll_detailed_label_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=L, value=L)
            for L in poll_store.Labels() if current.lower() in L.lower()][:25]
