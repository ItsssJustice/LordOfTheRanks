# /pollresults  --  the counts for a poll, once voting has closed.

@tree.command(
    name="pollresults",
    description="Show the results of a poll",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.describe(poll_id="The poll's ID, shown at the bottom of the poll message")
async def poll_results(interaction: discord.Interaction, poll_id: str):
    Record = poll_store.Find_By_Key(SQL_Cursor, poll_id)
    if Record is None:
        Known = [Key for Key, _ in poll_store.Recent_Choices(SQL_Cursor)][:10]
        await interaction.response.send_message(
            "No poll with ID '% s'. Recent poll ID(s): % s"
            % (poll_id, ", ".join(Known) if Known else "none yet"),
            ephemeral=True)
        return

    if not poll_store.Is_Closed(Record):
        Closes = discord.utils.format_dt(poll_store.As_Aware(Record["closes_at"]), "R")
        await interaction.response.send_message(
            "**% s** is still open. Results are shown once voting closes, %s."
            % (Record["question"], Closes), ephemeral=True)
        return

    Tally, Voter_Count = poll_store.Tally(Record)
    Total = sum(Count for _, Count in Tally)
    Lines = [poll_view.Reference(Record),
             "_Closed_ | %d vote(s) from %d member(s)" % (Total, Voter_Count), ""]
    for Text, Count in Tally:
        Lines.append(poll_format.Result_Line(Text, Count, Total))
    Lines.append("")
    Lines.append(poll_format.Outcome(Tally))

    await interaction.response.send_message("\n".join(Lines), ephemeral=True)


@poll_results.autocomplete("poll_id")
async def poll_results_id_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=Display, value=Key)
            for Key, Display in poll_store.Recent_Choices(SQL_Cursor, current)][:25]
