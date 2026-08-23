# /pollresults  --  read the answers back off a poll created earlier.
#
# THE IMPORTANT GOTCHA:
# A Poll object hangs off a Message, and a cached Message keeps whatever vote
# counts it had when the bot first saw it. To get live numbers you must pull a
# FRESH copy from the API with channel.fetch_message(id). That is the whole
# reason poll_store bothers to remember the channel id and message id.
#
# API being demonstrated:
#   await channel.fetch_message(id)   -> Message
#   Message.poll                      -> Poll or None
#   Poll.answers                      -> list of PollAnswer (.id .text .vote_count)
#   Poll.total_votes                  -> int (a property, NOT a method)
#   Poll.is_finalised()               -> bool, True once voting has closed
#   Poll.victor_answer                -> unreliable here, see Functions/poll_format.py
#
# Deliberately counts-only. Who voted for what lives in /polldetailedresults,
# which is permission-gated -- see Commands/Poll_Detailed_Results.py

@tree.command(
    name="pollresults",
    description="Fetch the current results of a poll created with /pollcreate",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.describe(label="The nickname you gave the poll when you created it")
async def poll_results(interaction: discord.Interaction, label: str):
    Record = poll_store.Find(label)
    if Record is None:
        Known = poll_store.Labels()
        await interaction.response.send_message(
            "No poll labelled '% s'. Known polls: % s" % (label, ", ".join(Known) if Known else "none yet"),
            ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    Channel = client.get_channel(Record["channel_id"])
    if Channel is None:
        try:
            Channel = await client.fetch_channel(Record["channel_id"])
        except discord.NotFound:
            await interaction.followup.send("That poll's channel no longer exists.", ephemeral=True)
            return

    # The fetch that actually refreshes the vote counts
    try:
        Poll_Message = await Channel.fetch_message(Record["message_id"])
    except discord.NotFound:
        await interaction.followup.send("The poll message was deleted.", ephemeral=True)
        return
    except discord.Forbidden:
        await interaction.followup.send(
            "I can't read history in that channel. I need 'Read Message History' there.", ephemeral=True)
        return

    Poll = Poll_Message.poll
    if Poll is None:
        await interaction.followup.send("That message doesn't carry a poll any more.", ephemeral=True)
        return

    Total = Poll.total_votes
    Closed = Poll.is_finalised()

    Lines = []
    Lines.append("**% s**" % Poll.question)
    Lines.append("_% s_ | %d vote(s) total | closes %s" % (
        "Closed" if Closed else "Open",
        Total,
        discord.utils.format_dt(Poll.expires_at, "R") if Poll.expires_at else "never"))
    Lines.append("")

    for Answer in Poll.answers:
        # Guard the divide so an untouched poll doesn't blow up
        Bar, Share = poll_format.Bar(Answer.vote_count, Total)
        Lines.append("`%-3d` %s  %s %.0f%%" % (Answer.vote_count, Answer.text, Bar, Share))

    # Worked out from the vote counts, because Poll.victor_answer is not
    # populated on a poll fetched this way. See Functions/poll_format.py
    if Closed:
        Lines.append("")
        Lines.append(poll_format.Outcome(Poll))

    Lines.append(Poll_Message.jump_url)

    await interaction.followup.send("\n".join(Lines), ephemeral=True)


# Autocomplete so testers don't have to remember the labels they used
@poll_results.autocomplete("label")
async def poll_results_label_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=Label, value=Label)
        for Label in poll_store.Labels()
        if current.lower() in Label.lower()
    ][:25]
