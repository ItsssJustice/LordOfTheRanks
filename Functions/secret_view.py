# The button ballot.
#
# Each button carries a custom_id of "sp:<label>:<index>". discord.py routes an
# interaction back to us by matching that id, which is what lets these buttons
# keep working after the bot restarts -- see Register_Open in PollTest.py.
#
# The posted message is deliberately NOT edited as votes come in. Two reasons:
# editing on every click would burn through the channel edit rate limit, and a
# live ballot counter is one more thing that could hint at how voting is going.
# The message is only rewritten once, when the poll closes.

import discord
from . import secret_store

BUTTON_STYLES = [discord.ButtonStyle.secondary, discord.ButtonStyle.primary]

class Ballot_Button(discord.ui.Button):
    def __init__(self, Poll_Label, Index, Text):
        super().__init__(
            label=Text[:80],
            style=discord.ButtonStyle.secondary,
            custom_id="sp:%s:%d" % (Poll_Label.lower(), Index),
            row=Index // 5
        )
        self.Poll_Label = Poll_Label
        self.Index = Index

    async def callback(self, interaction: discord.Interaction):
        Accepted, Note = secret_store.Record_Vote(self.Poll_Label, interaction.user.id, self.Index)
        # Always ephemeral: the voter is the only person who ever sees this
        await interaction.response.send_message(Note, ephemeral=True)

class Ballot(discord.ui.View):
    def __init__(self, Poll_Label, Answers):
        super().__init__(timeout=None)          # required for a persistent view
        for i, Text in enumerate(Answers[:25]):
            self.add_item(Ballot_Button(Poll_Label, i, Text))

def Build_Embed(Record):
    """The public face of the poll. Never contains anything vote-identifying."""
    Closed = secret_store.Is_Closed(Record)
    Embed = discord.Embed(
        title=Record["question"],
        colour=discord.Colour(0x2b2d31) if Closed else discord.Colour(0x5865F2)
    )

    if Closed:
        Tally, Ballots = secret_store.Tally(Record)
        Total = sum(c for _, c in Tally)
        Lines = []
        for Text, Count in Tally:
            Share = (Count / Total * 100) if Total else 0
            Lines.append("`%-3d` %s  %s %.0f%%" % (Count, Text, "#" * int(Share / 5), Share))
        Embed.description = "\n".join(Lines) if Lines else "_no options_"
        Embed.set_footer(text="Voting closed - %d ballot(s) cast" % Ballots)
    else:
        Embed.description = "\n".join("- %s" % Text for Text in Record["answers"])
        Embed.add_field(
            name="​",
            value=("Secret ballot: nobody can see how you voted while this is open, "
                   "not even staff.\n%s vote(s) allowed per person."
                   % ("Multiple" if Record["multiple"] else "One")),
            inline=False)
        Closes = discord.utils.format_dt(
            discord.utils.parse_time(Record["closes_at"]), "R")
        Embed.set_footer(text="Closes")
        Embed.timestamp = discord.utils.parse_time(Record["closes_at"])
    return Embed

async def Refresh_Message(client, Record):
    """Rewrite the posted message, e.g. once the poll has closed."""
    if not Record.get("message_id"):
        return
    Channel = client.get_channel(Record["channel_id"])
    if Channel is None:
        try:
            Channel = await client.fetch_channel(Record["channel_id"])
        except Exception:
            return
    try:
        Message = await Channel.fetch_message(Record["message_id"])
    except Exception:
        return
    View = None if secret_store.Is_Closed(Record) else Ballot(Record["label"], Record["answers"])
    await Message.edit(embed=Build_Embed(Record), view=View)
