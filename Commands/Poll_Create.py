# /pollcreate  --  post a native Discord poll into a specific channel.
#
# The key bits of the discord.py API being demonstrated here:
#   discord.Poll(question=..., duration=..., multiple=...)
#   Poll.add_answer(text=..., emoji=...)
#   await channel.send(poll=...)      <- a poll rides along on a normal message
#
# Discord's own limits (the API will 400 if you break them):
#   question   <= 300 characters
#   answer     <= 55 characters, between 1 and 10 answers
#   duration   between 1 and 768 hours (32 days)

@tree.command(
    name="pollcreate",
    description="Create a poll in a specific channel",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.describe(
    label="Short nickname you'll use to fetch the results later, e.g. 'raidnight'",
    channel="The channel to post the poll into",
    question="The poll question",
    answers="Answer options separated by | for example: Monday | Tuesday | Wednesday",
    hours="How long the poll stays open, 1 to 768 hours (default 24)",
    multiple="Allow each member to pick more than one answer (default False)"
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
    # Split "A | B | C" into a clean list, dropping any empty entries
    Answer_List = [Option.strip() for Option in answers.split("|") if Option.strip()]

    # Validate locally so testers get a readable error instead of an HTTP 400
    if len(Answer_List) < 1 or len(Answer_List) > 10:
        await interaction.response.send_message(
            "A poll needs between 1 and 10 answers, I counted % d. Separate them with |" % len(Answer_List),
            ephemeral=True)
        return
    Too_Long = [Option for Option in Answer_List if len(Option) > 55]
    if Too_Long:
        await interaction.response.send_message(
            "These answers are over Discord's 55 character limit: " + ", ".join(Too_Long), ephemeral=True)
        return
    if len(question) > 300:
        await interaction.response.send_message(
            "The question is over Discord's 300 character limit.", ephemeral=True)
        return
    if hours < 1 or hours > 768:
        await interaction.response.send_message(
            "Duration must be between 1 and 768 hours (32 days).", ephemeral=True)
        return
    if poll_store.Find(label):
        await interaction.response.send_message(
            "There's already a poll labelled '% s'. Pick another label." % label, ephemeral=True)
        return

    # Build the poll object, then hang the answers off it
    New_Poll = discord.Poll(
        question=question,
        duration=datetime.timedelta(hours=hours),
        multiple=multiple
    )
    for Option in Answer_List:
        New_Poll.add_answer(text=Option)

    # A poll is sent as part of a message; one poll per message, bots may not
    # attach a poll to a message that also carries content or embeds.
    try:
        Poll_Message = await channel.send(poll=New_Poll)
    except discord.Forbidden:
        await interaction.response.send_message(
            "I'm missing permissions in % s. I need 'View Channel', 'Send Messages' and 'Create Polls' there."
            % channel.mention, ephemeral=True)
        return
    except discord.HTTPException as Error:
        await interaction.response.send_message("Discord rejected the poll: % s" % Error, ephemeral=True)
        return

    # Remember where it landed so /pollresults can find it after a restart
    poll_store.Save(label, interaction.guild_id, channel.id, Poll_Message.id, question, Answer_List)

    await interaction.response.send_message(
        "Poll '% s' posted in % s.\nRead it back later with `/pollresults label:% s`\n%s"
        % (label, channel.mention, label, Poll_Message.jump_url),
        ephemeral=True)
