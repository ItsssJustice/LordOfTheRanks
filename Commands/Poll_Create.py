# /pollcreate  --  post a poll into a channel.
#
# The poll is a message with one button per answer. A click is an interaction
# that comes to this bot, and the vote is written to Polls.json. Results are
# shown once voting closes.
#
# This is the plain poll: a question and some answers, nothing more. It carries
# no subject and no role, so /pollgrant cannot act on it. Anything that changes
# somebody's rank goes through /startpromotionvote or /startdemotionvote, which
# are permission-gated; a generic poll may be opened up much more widely.
#
# Limits come from discord's component rules: button labels max out at 80
# characters, and a message carries at most 25 buttons.

@tree.command(
    name="pollcreate",
    description="Create a poll in a specific channel",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="Short nickname used to fetch results later",
    channel="The channel to post the poll into",
    question="The poll question",
    answers="Options separated by | for example: Yes | No | Abstain",
    hours="How long voting stays open, 1 to 768 hours (default 24)",
    multiple="Let each member pick more than one option (default False)"
)
async def poll_create(
    interaction: discord.Interaction,
    label: str,
    channel: discord.TextChannel,
    question: str,
    answers: str,
    hours: int = 24,
    multiple: bool = False
):
    Answer_List = [O.strip() for O in answers.split("|") if O.strip()]

    if len(label) > poll_store.LABEL_LIMIT:
        await interaction.response.send_message(
            "Label must be %d characters or fewer, that one is %d.\nA custom emoji counts for "
            "about thirty characters on its own, because discord sends it to me as "
            "`<:name:1234567890123456789>`."
            % (poll_store.LABEL_LIMIT, len(label)), ephemeral=True)
        return
    if len(Answer_List) < 2 or len(Answer_List) > 25:
        await interaction.response.send_message(
            "A poll needs between 2 and 25 answers, I counted % d. Separate them with |"
            % len(Answer_List), ephemeral=True)
        return
    Too_Long = [O for O in Answer_List if len(O) > 80]
    if Too_Long:
        await interaction.response.send_message(
            "Answers max out at 80 characters: " + ", ".join(Too_Long), ephemeral=True)
        return
    if len(question) > 256:
        await interaction.response.send_message(
            "The question must be 256 characters or fewer, that one is %d." % len(question),
            ephemeral=True)
        return
    if hours < 1 or hours > 768:
        await interaction.response.send_message("Duration must be 1 to 768 hours.", ephemeral=True)
        return
    if poll_store.Find(label):
        await interaction.response.send_message(
            "The label '% s' is already in use." % label, ephemeral=True)
        return

    Record = poll_store.Create(label, interaction.guild_id, channel.id, question,
                               Answer_List, multiple, hours)

    try:
        Message = await channel.send(embed=poll_view.Build_Embed(Record),
                                     view=poll_view.Poll_Buttons(Record["key"], Answer_List))
    except discord.Forbidden:
        await interaction.response.send_message(
            "I'm missing permissions in % s. I need 'View Channel' and 'Send Messages' there."
            % channel.mention, ephemeral=True)
        return

    poll_store.Attach_Message(label, Message.id)

    await interaction.response.send_message(
        "Poll '% s' posted in % s.\nRead it back later with `/pollresults label:% s`\n%s%s"
        % (label, channel.mention, label, Message.jump_url,
           poll_view.Emoji_Warning(interaction.client, label, question, answers)),
        ephemeral=True)
