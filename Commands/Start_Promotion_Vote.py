# /startpromotionvote  --  open a vote on moving a member one rank up.
#
# The target rank comes from the ladder in Functions/rank_ladder.py, not from
# whoever runs the command, so a vote cannot propose a rank that is two steps
# away or not a rank at all. Someone already at the top has nothing to move to
# and the command says so.

@tree.command(
    name="startpromotionvote",
    description="Open a vote on promoting a member one rank",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    label="Short nickname used to fetch results later",
    member="The member being voted on",
    channel="The channel to post the vote into",
    hours="How long voting stays open, 1 to 768 hours (default 24)",
    role="Which rank to promote to. Leave empty for the next one on the ladder"
)
async def start_promotion_vote(
    interaction: discord.Interaction,
    label: str,
    member: discord.Member,
    channel: discord.TextChannel,
    hours: int = 24,
    role: discord.Role = None
):
    await rank_vote.Start(interaction.client, interaction, rank_ladder.PROMOTION, label, member, channel, hours, Role=role)
