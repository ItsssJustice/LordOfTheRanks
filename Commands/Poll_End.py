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
@app_commands.describe(poll_id="The poll's ID, shown at the bottom of the poll message")
async def poll_end(interaction: discord.Interaction, poll_id: str):
    Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
    if Record is None:
        await interaction.response.send_message("No poll with ID '% s'." % poll_id, ephemeral=True)
        return
    if poll_store.Is_Closed(Record):
        await interaction.response.send_message("That poll is already closed.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    Record = poll_store.Close(SQL_Connection, SQL_Cursor, Record["poll_id"])
    await poll_view.Refresh_Message(SQL_Connection, SQL_Cursor, interaction.client, Record)

    Tally, Voter_Count = poll_store.Tally(Record)
    Lines = ["Closed %s" % poll_view.Reference(Record),
             "%d member(s) voted" % Voter_Count]
    for Text, Count in Tally:
        Lines.append("  %d - %s" % (Count, Text))
    Lines.append(poll_format.Outcome(Tally))
    await interaction.followup.send("\n".join(Lines), ephemeral=True)


@poll_end.autocomplete("poll_id")
async def poll_end_id_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=Display, value=Key)
            for Key, Display in poll_store.Open_Choices(SQL_Cursor, current)][:25]
