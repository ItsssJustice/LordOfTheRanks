@tree.command(
    name="test",
    description="Test Command",
    guild=discord.Object(id=DISCORD_GUILD)
)
async def first_command(interaction):
    await interaction.response.send_message("Hello!")