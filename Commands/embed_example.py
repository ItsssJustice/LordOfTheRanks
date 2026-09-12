# /embedtest  --  posts a sample embed showing off the formatting options available,
# built entirely through bot_config.Build so it also exercises the
# character-limit trimming and console logging in that function.
#
# Not gated behind default_permissions: it's a display example, not something
# that changes state, so there's no reason to restrict it to moderators.
@tree.command(
    name="embedtest",
    description="Post a sample embed showing the available formatting options",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.describe(ephemeral="Only show it to you (default False)")
async def embed_test(interaction: discord.Interaction, ephemeral: bool = False):
    Description = (
        "This is the embed **description**. It supports the same markdown as a normal "
        "message: *italics*, **bold**, ***bold italics***, __underline__, ~~strikethrough~~, "
        "`inline code`, and [masked links](https://discord.com).\n\n"
        "```py\n# and fenced code blocks\nprint('Hello, World!')\n```"
    )
    Fields = [
        # (name, value, inline)
        ("Inline Field 1", "Sits side-by-side\nwith the next field.", True),
        ("Inline Field 2", "Discord fits 3 inline\nfields per row.", True),
        ("Inline Field 3", "This one wraps to\nrow 2 if there's a 4th.", True),
        ("Non-inline field", "This one takes the full width of the embed, useful for "
                             "longer content that shouldn't be squeezed into a column.",
         False),
        {"name": "Dict-style field", "value": "Fields can also be passed as dicts.",
         "inline": True},
        ("Emoji + formatting", "✅ Checkmarks, ⚠️ warnings, 🔗 links - anything unicode "
                               "works directly. Custom server emoji work too: <:name:id>.",
         True),
    ]
    Embed = embed_handling.Build(
        title="Embed Formatting Example",
        description=Description,
        colour=discord.Colour.blurple(),
        fields=Fields,
        footer="Requested by %s" % interaction.user.display_name,
        author_name=interaction.client.user.display_name,
        author_icon_url=interaction.client.user.display_avatar.url,
        thumbnail_url=interaction.user.display_avatar.url,
        url="https://discord.com",
        timestamp=discord.utils.utcnow()
    )
    Message = await embed_handling.Send(interaction, Embed, ephemeral=ephemeral)
    if Message is None:
        # Embed_Send already printed the reason to console; interaction still needs a reply
        # if it never got sent, so the command doesn't just hang from the caller's side.
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong sending that embed, check the console log.",
                ephemeral=True)

# /embedtestpaginated  --  posts a multi-page embed to show off Embed_Paginate +
# Embed_Send's pagination handling, distinct from /embedtest which only covers
# formatting inside a single page.
#
# Not gated behind default_permissions, same reasoning as /embedtest: it's a
# display example, nothing here changes state.

@tree.command(
    name="embedtestpaginated",
    description="Post a paginated sample embed to show off Embed_Paginate",
    guild=discord.Object(id=DISCORD_GUILD)
)
@app_commands.describe(fields_per_page="How many fields to show per page (default 4)")
async def embed_test_paginated(interaction: discord.Interaction, fields_per_page: int = 4):
    # Deliberately more fields than fit on one page, so the split is visible.
    # Each names its own index so it's obvious which page you landed on.
    Fields = [
        ("Field %d" % i,
         "This is the content for field %d.\nA field can span multiple lines." % i,
         (i % 2 == 0))  # alternate inline/non-inline so both are visible across pages
        for i in range(1, 13)
    ]
    Pages = embed_handling.Paginate(
        title="Paginated Embed Example",
        description="This embed's fields have been split across several pages because "
                    "there are more of them than comfortably fit on one.",
        colour=discord.Colour.gold(),
        fields=Fields,
        fields_per_page=max(1, fields_per_page),
        footer="Requested by %s" % interaction.user.display_name,
    )
    Menu = await embed_handling.Send(interaction, Pages, ephemeral=False)
    if Menu is None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong sending that embed, check the console log.",
                ephemeral=True)

async def _Like_Button_Clicked(interaction: discord.Interaction, view):
    # Counter lives on the view itself, so each message tracks its own count independently.
    view.Like_Count = getattr(view, "Like_Count", 0) + 1
    Updated = embed_handling.Build(
        title="Buttons Example",
        description="Press the buttons below - each one runs its own handler in "
                    "Commands/embed_test.py, embed_handling just wired up the click.",
        colour=discord.Colour.green(),
        fields=[("👍 Likes", str(view.Like_Count), True)]
    )
    await interaction.response.edit_message(embed=Updated, view=view)

async def _Confirm_Button_Clicked(interaction: discord.Interaction, view):
    await interaction.response.send_message(
        "You clicked Confirm - this reply is private to you.", ephemeral=True)

async def _Danger_Button_Clicked(interaction: discord.Interaction, view):
    await interaction.response.send_message(
        "This button is styled danger.red but doesn't actually delete anything here - "
        "just demonstrating the style option.", ephemeral=True)

@tree.command(
    name="embedtestbuttons",
    description="Post a sample embed with custom extra buttons",
    guild=discord.Object(id=DISCORD_GUILD)
)
async def embed_test_buttons(interaction: discord.Interaction):

    Embed = embed_handling.Build(
        title="Buttons Example",
        description="Press the buttons below - each one runs its own handler in "
                    "Commands/embed_test.py, embed_handling just wired up the click.",
        colour=discord.Colour.green(),
        fields=[("👍 Likes", "0", True)]
    )

    Extra_Buttons = [
        {"label": "Like", "emoji": "👍", "style": discord.ButtonStyle.success,
         "callback": _Like_Button_Clicked},
        {"label": "Confirm", "style": discord.ButtonStyle.primary,
         "callback": _Confirm_Button_Clicked},
        {"label": "Danger", "style": discord.ButtonStyle.danger,
         "callback": _Danger_Button_Clicked},
        {"label": "Docs", "emoji": "🔗", "url": "https://discordpy.readthedocs.io"},
    ]

    View = await embed_handling.Send(interaction, Embed, extra_buttons=Extra_Buttons)
    if View is None and not interaction.response.is_done():
        await interaction.response.send_message(
            "Something went wrong sending that embed, check the console log.", ephemeral=True)