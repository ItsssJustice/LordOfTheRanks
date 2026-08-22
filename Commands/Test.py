@tree.command(
    name="test",
    description="Test Command",
    guild=discord.Object(id=ENV_GUILD)
)
async def first_command(interaction):
    await interaction.response.send_message("Hello!")