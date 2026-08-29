# /startdemotionvote  --  open a vote on moving a member one rank down.
#
# Mirrors /startpromotionvote. Someone already at the bottom of the ladder has
# nothing to move to and the command says so.

@tree.command(
    name="startdemotionvote",
    description="Open a vote on demoting a member one rank",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="Short nickname used to fetch results later",
    member="The member being voted on",
    channel="The channel to post the vote into",
    hours="How long voting stays open, 1 to 768 hours (default 24)",
    role="Which rank to demote to. Leave empty for the next one on the ladder"
)
async def start_demotion_vote(
    interaction: discord.Interaction,
    label: str,
    member: discord.Member,
    channel: discord.TextChannel,
    hours: int = 24,
    role: discord.Role = None
):
    await rank_vote.Start(interaction.client, interaction, rank_ladder.DEMOTION, label, member, channel, hours, Role=role)
