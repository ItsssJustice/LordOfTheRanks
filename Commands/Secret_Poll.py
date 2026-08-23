# /secretpoll  --  a poll where nobody can see how anyone voted.
#
# Not a native discord Poll. This posts an ordinary message with buttons, and
# keeps the votes in SecretPolls.json on this machine. That is the whole point:
# a native poll's voter list is exposed by discord's own client and cannot be
# hidden, so a genuinely secret ballot has to be recorded bot-side.
#
# Trade-offs versus /pollcreate: no native poll UI, and expiry is enforced by
# this bot rather than by discord (see the closer task in PollTest.py).

@tree.command(
    name="secretpoll",
    description="Create a secret-ballot poll where nobody can see who voted for what",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="Short nickname used to fetch results later, max 32 characters",
    channel="The channel to post the ballot into",
    question="The poll question",
    answers="Options separated by | for example: Yes | No | Abstain",
    hours="How long voting stays open, 1 to 768 hours (default 24)",
    multiple="Let each member pick more than one option (default False)"
)
async def secret_poll(
    interaction: discord.Interaction,
    label: str,
    channel: discord.TextChannel,
    question: str,
    answers: str,
    hours: int = 24,
    multiple: bool = False
):
    Answer_List = [O.strip() for O in answers.split("|") if O.strip()]

    if len(label) > 32:
        await interaction.response.send_message(
            "Label must be 32 characters or fewer (it goes inside the button ids).", ephemeral=True)
        return
    if len(Answer_List) < 2 or len(Answer_List) > 25:
        await interaction.response.send_message(
            "A secret poll needs between 2 and 25 answers, I counted % d. Separate them with |"
            % len(Answer_List), ephemeral=True)
        return
    Too_Long = [O for O in Answer_List if len(O) > 80]
    if Too_Long:
        await interaction.response.send_message(
            "Button labels max out at 80 characters: " + ", ".join(Too_Long), ephemeral=True)
        return
    if hours < 1 or hours > 768:
        await interaction.response.send_message("Duration must be 1 to 768 hours.", ephemeral=True)
        return
    if secret_store.Find(label) or poll_store.Find(label):
        await interaction.response.send_message(
            "The label '% s' is already in use." % label, ephemeral=True)
        return

    Record = secret_store.Create(label, interaction.guild_id, channel.id, question,
                                 Answer_List, multiple, False, hours)

    View = secret_view.Ballot(label, Answer_List)
    try:
        Message = await channel.send(embed=secret_view.Build_Embed(Record), view=View)
    except discord.Forbidden:
        await interaction.response.send_message(
            "I'm missing permissions in % s. I need 'View Channel' and 'Send Messages' there."
            % channel.mention, ephemeral=True)
        return

    secret_store.Attach_Message(label, Message.id)

    await interaction.response.send_message(
        "Secret ballot '% s' posted in % s.\n"
        "Counts: `/secretpollresults label:% s`  |  Who voted: `/secretpolldetailed label:% s`\n%s"
        % (label, channel.mention, label, label, Message.jump_url),
        ephemeral=True)
