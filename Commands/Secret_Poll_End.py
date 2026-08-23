# /secretpollend  --  close a secret ballot early.
#
# Closing rewrites the posted message to show the final counts and removes the
# buttons, so the result becomes public at the moment voting stops.

@tree.command(
    name="secretpollend",
    description="Close a secret ballot now and publish the counts",
    guild=discord.Object(id=ENV_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(label="The ballot's nickname")
async def secret_poll_end(interaction: discord.Interaction, label: str):
    Record = secret_store.Find(label)
    if Record is None:
        await interaction.response.send_message("No secret poll labelled '% s'." % label, ephemeral=True)
        return
    if secret_store.Is_Closed(Record):
        await interaction.response.send_message("That ballot is already closed.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    Record = secret_store.Close(label)
    await secret_view.Refresh_Message(client, Record)

    Tally, Ballots = secret_store.Tally(Record)
    Lines = ["Closed **%s** - %d ballot(s)" % (Record["question"], Ballots)]
    for Text, Count in Tally:
        Lines.append("  %d - %s" % (Count, Text))
    await interaction.followup.send("\n".join(Lines), ephemeral=True)


@secret_poll_end.autocomplete("label")
async def secret_end_ac(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=L, value=L)
            for L in secret_store.Open_Labels() if current.lower() in L.lower()][:25]
