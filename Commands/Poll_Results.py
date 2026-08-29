# /pollresults  --  the counts for a poll, once voting has closed.

@tree.command(
    name="pollresults",
    description="Show the results of a poll",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.describe(label="The poll's nickname")
async def poll_results(interaction: discord.Interaction, label: str):
    Record = poll_store.Find(label)
    if Record is None:
        Known = poll_store.Labels()
        await interaction.response.send_message(
            "No poll labelled '% s'. Known polls: % s" % (label, ", ".join(Known) if Known else "none yet"),
            ephemeral=True)
        return

    if not poll_store.Is_Closed(Record):
        Closes = discord.utils.format_dt(discord.utils.parse_time(Record["closes_at"]), "R")
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


@poll_results.autocomplete("label")
async def poll_results_label_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=L, value=L)
            for L in poll_store.Recent_Labels(current)][:25]
