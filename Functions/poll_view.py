# The answer buttons and the posted message.
#
# Each button carries a custom_id of "poll:<key>:<index>", where key is the short
# id poll_store hands out. discord.py routes an interaction back here by matching
# that id, which is what lets the buttons keep working after the bot restarts --
# see the re-registration in PollTest.py.
#
# The key is deliberately NOT the label. discord caps a custom_id at 100
# characters, and a label can be long, or hold a custom emoji, which arrives as
# "<:name:1234567890123456789>" and eats about thirty characters on its own.
# Keeping them separate means the label is free to be whatever reads well.
#
# WHY THE PUBLIC BUTTONS NEVER CHANGE COLOUR:
# a message's components are shared by everyone who can see the message, so
# marking someone's choice on the posted poll would mark it for the whole
# channel. Instead, clicking answers privately with a copy of the buttons in
# which that member's own choice is green. Only they can see it, and they can
# keep clicking there to change their mind without touching the public message.
#
# The posted message itself is not edited as votes come in. Editing on every
# click would run into the channel edit rate limit, and it has nothing new to
# show until voting is over. It is rewritten once, when the poll closes.

import re
import discord
from . import poll_store, poll_format

# A custom emoji reaches us as markup: <:name:id>, or <a:name:id> when animated.
CUSTOM_EMOJI = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")

def Strip_Emoji(Text):
    """Remove custom emoji markup, for the places discord will not render it.

    An embed's title and its footer text are plain text: only unicode emoji show
    up there, and a custom one is left as raw "<:name:id>". Rather than print
    that at people, drop it.
    """
    return CUSTOM_EMOJI.sub("", Text).strip()

def Unusable_Emoji(client, *Texts):
    """Custom emoji in these strings that this bot cannot render in message text.

    A bot may only use a custom emoji from a server it is itself a member of.
    Anyone with nitro can type one from any server *they* are in, and discord
    hands us the markup happily, but when the bot posts that markup back discord
    falls back to plain ":name:" text.

    Components are not affected, which is why a button can show an emoji that the
    embed above it cannot. Returns the names, so the poll's creator can be told
    rather than finding out from the posted message.
    """
    Names = []
    for Text in Texts:
        for Markup in CUSTOM_EMOJI.findall(Text or ""):
            Emoji = discord.PartialEmoji.from_str(Markup)
            if Emoji.id is not None and client.get_emoji(Emoji.id) is None:
                Names.append(Emoji.name)
    return sorted(set(Names))

def Emoji_Warning(client, *Texts):
    """A sentence naming the emoji this bot cannot use, or "" if they are all fine."""
    Names = Unusable_Emoji(client, *Texts)
    if not Names:
        return ""
    return ("\nHeads up: %s will show as text, not as %s. A bot can only use emoji "
            "from servers it is in - invite me to the server they came from, or copy them "
            "into this one."
            % (", ".join("`:%s:`" % N for N in Names),
               "an image" if len(Names) == 1 else "images"))

def Split_Emoji(Text):
    """Separate a leading custom emoji from an answer's text.

    A button's label is plain text -- discord does not render <:name:id> markup
    inside it, so an answer written with a custom emoji would show the raw markup.
    Emoji have to go in the button's own emoji field instead, and a button takes
    exactly one. Unicode emoji need none of this; they are ordinary characters
    and render in a label as they are.

    Returns (label, emoji) where either may be None, but never both.
    """
    Found = CUSTOM_EMOJI.search(Text)
    if not Found:
        return Text[:80], None
    # Collapse the gap the markup leaves behind, so "No - stay <:x:1> Sergeant"
    # does not become "No - stay  Sergeant" with a double space.
    Label = re.sub(r"\s{2,}", " ", CUSTOM_EMOJI.sub("", Text)).strip()
    Emoji = discord.PartialEmoji.from_str(Found.group(0))
    return (Label[:80] or None), Emoji

class Answer_Button(discord.ui.Button):
    def __init__(self, Poll_Key, Index, Text, Selected=False):
        Label, Emoji = Split_Emoji(Text)
        super().__init__(
            label=Label,
            emoji=Emoji,
            style=discord.ButtonStyle.success if Selected else discord.ButtonStyle.secondary,
            custom_id="poll:%s:%d" % (Poll_Key, Index),
            row=Index // 5
        )
        self.Poll_Key = Poll_Key
        self.Index = Index

    async def callback(self, interaction: discord.Interaction):
        Accepted, Note = poll_store.Record_Vote(self.Poll_Key, interaction.user.id, self.Index)
        Record = poll_store.Find_By_Key(self.Poll_Key)
        # Name the poll first: a member can have several open at once, and
        # "Vote changed from Yes to No" alone says nothing about which.
        Lead = (Reference(Record) + "\n") if Record else ""

        # Poll closed or gone: say so, and drop the buttons if we are already
        # inside the member's private copy.
        if not Accepted or Record is None:
            if _Is_Private_Copy(interaction):
                await interaction.response.edit_message(content=Lead + Note, view=None)
            else:
                await interaction.response.send_message(Lead + Note, ephemeral=True)
            return

        Picks = Record["votes"].get(str(interaction.user.id), [])
        Body = "%s%s\n\n%s" % (Lead, Note, Vote_Summary(Record, Picks))
        View = Poll_Buttons(self.Poll_Key, Record["answers"], Picks)

        if _Is_Private_Copy(interaction):
            await interaction.response.edit_message(content=Body, view=View)
        else:
            await interaction.response.send_message(Body, view=View, ephemeral=True)

def _Is_Private_Copy(interaction):
    """True when the click came from the member's own ephemeral copy of the buttons."""
    Message = interaction.message
    return Message is not None and Message.flags.ephemeral

def Reference(Record):
    """A short line naming the poll.

    A member can have several polls open at once, and a bare "Vote changed from
    ok to arrow" says nothing about which one it belongs to.
    """
    Question = Record["question"]
    if len(Question) > 200:
        Question = Question[:197] + "..."
    return "**%s**  ·  `%s`" % (Question, Strip_Emoji(Record["label"]))

def Vote_Summary(Record, Picks):
    """One line telling a member what they currently have recorded."""
    if not Picks:
        return "You have no vote recorded."
    Chosen = [Record["answers"][i] for i in Picks if 0 <= i < len(Record["answers"])]
    if len(Chosen) == 1:
        return "Your vote: **%s** (shown in green below)" % Chosen[0]
    return "Your votes: %s (shown in green below)" % ", ".join("**%s**" % C for C in Chosen)

class Poll_Buttons(discord.ui.View):
    """The answer buttons. Picks are highlighted, which is only ever used for a
    member's private copy -- the public message passes no picks."""
    def __init__(self, Poll_Key, Answers, Picks=()):
        super().__init__(timeout=None)          # required for a persistent view
        for i, Text in enumerate(Answers[:25]):
            self.add_item(Answer_Button(Poll_Key, i, Text, Selected=(i in Picks)))

def _Started_By(Record):
    """Credit line, or "" when the record predates it being kept.

    Deliberately the only thing said about a rank vote beyond its question and
    answers: the question already names the member and both ranks, and each
    answer names the rank it leads to, so repeating the move again in a field
    was the third telling of the same fact.
    """
    if not Record.get("started_by_name"):
        return ""
    return "\n\nVote started by %s" % Record["started_by_name"]

def Build_Embed(Record):
    """The posted message. Shows the answers while open, the counts once closed."""
    Closed = poll_store.Is_Closed(Record)
    Embed = discord.Embed(
        colour=discord.Colour(0x2b2d31) if Closed else discord.Colour(0x5865F2)
    )
    # The question leads the description rather than filling the title, because
    # an embed title will not render a custom emoji and a description will.
    Heading = "**%s**" % Record["question"]

    if Closed:
        Tally, Voter_Count = poll_store.Tally(Record)
        Total = sum(Count for _, Count in Tally)
        Lines = []
        for Text, Count in Tally:
            Lines.append(poll_format.Result_Line(Text, Count, Total))
        # Credit and result share one block under the bars, so the blank line
        # above them does not depend on whether a credit line exists.
        Closing = []
        if Record.get("started_by_name"):
            Closing.append("Vote started by %s" % Record["started_by_name"])
        Closing.append("Result: " + (poll_format.Rank_Result(Tally)
                                     if poll_store.Is_Rank_Vote(Record)
                                     else poll_format.Short_Result(Tally)))
        Embed.description = (Heading + "\n\n"
                             + ("\n".join(Lines) if Lines else "_no options_")
                             + "\n\n" + "\n".join(Closing))
        Embed.set_footer(text="%s  -  voting closed, %d member(s) voted"
                              % (Strip_Emoji(Record["label"]), Voter_Count))
    else:
        Embed.description = (Heading + "\n\n"
                             + "\n".join("- %s" % Text for Text in Record["answers"])
                             + _Started_By(Record))
        Embed.add_field(
            name="​",
            value=("Click an answer to vote. Your choice is confirmed privately, "
                   "and you can change it until voting closes.\n%s answer(s) per person."
                   % ("Multiple" if Record["multiple"] else "One")),
            inline=False)
        Embed.set_footer(text="%s  -  closes" % Strip_Emoji(Record["label"]))
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
    View = None if poll_store.Is_Closed(Record) else Poll_Buttons(Record["key"], Record["answers"])
    await Message.edit(embed=Build_Embed(Record), view=View)
