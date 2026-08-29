# /pollend  --  close a poll before its time is up.
#
# Closing rewrites the posted message with the counts and removes the buttons,
# so the result becomes visible at the moment voting stops.

@tree.command(
    name="pollend",
    description="Close a poll now and publish the counts",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(label="The poll's nickname")
async def poll_end(interaction: discord.Interaction, label: str):
    Record = poll_store.Find(label)
    if Record is None:
        await interaction.response.send_message("No poll labelled '% s'." % label, ephemeral=True)
        return
    if poll_store.Is_Closed(Record):
        await interaction.response.send_message("That poll is already closed.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    Record = poll_store.Close(label)
    await poll_view.Refresh_Message(interaction.client, Record)

    Tally, Voter_Count = poll_store.Tally(Record)
    Lines = ["Closed %s" % poll_view.Reference(Record),
             "%d member(s) voted" % Voter_Count]
    for Text, Count in Tally:
        Lines.append("  %d - %s" % (Count, Text))
    Lines.append(poll_format.Outcome(Tally))
    await interaction.followup.send("\n".join(Lines), ephemeral=True)


@poll_end.autocomplete("label")
async def poll_end_label_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=L, value=L)
            for L in poll_store.Open_Labels() if current.lower() in L.lower()][:25]
