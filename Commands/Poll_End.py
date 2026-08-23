# /pollend  --  close a poll early instead of waiting for its duration to run out.
#
# API being demonstrated:
#   await Message.end_poll()   -> returns the updated Message, poll now finalised
#
# A bot may only end a poll it created itself, and once ended it cannot be reopened.
# Note the returned Message still has Poll.victor_answer == None; the winner is
# worked out from the vote counts in Functions/poll_format.py.

@tree.command(
    name="pollend",
    description="Close a poll early and show the final result",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.describe(label="The nickname you gave the poll when you created it")
async def poll_end(interaction: discord.Interaction, label: str):
    Record = poll_store.Find(label)
    if Record is None:
        await interaction.response.send_message("No poll labelled '% s'." % label, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    Channel = client.get_channel(Record["channel_id"])
    if Channel is None:
        Channel = await client.fetch_channel(Record["channel_id"])

    try:
        Poll_Message = await Channel.fetch_message(Record["message_id"])
    except discord.NotFound:
        await interaction.followup.send("The poll message was deleted.", ephemeral=True)
        return

    if Poll_Message.poll is None:
        await interaction.followup.send("That message doesn't carry a poll.", ephemeral=True)
        return
    if Poll_Message.poll.is_finalised():
        await interaction.followup.send("That poll is already closed.", ephemeral=True)
        return

    try:
        Poll_Message = await Poll_Message.end_poll()
    except discord.HTTPException as Error:
        await interaction.followup.send("Couldn't end the poll: % s" % Error, ephemeral=True)
        return

    Poll = Poll_Message.poll
    Summary = ["Closed **% s**" % Poll.question]
    for Answer in Poll.answers:
        Summary.append("  %d - %s" % (Answer.vote_count, Answer.text))
    Summary.append(poll_format.Outcome(Poll))

    await interaction.followup.send("\n".join(Summary), ephemeral=True)


@poll_end.autocomplete("label")
async def poll_end_label_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=Label, value=Label)
        for Label in poll_store.Labels()
        if current.lower() in Label.lower()
    ][:25]
