# Opening a promotion or demotion vote.
#
# Both commands do the same thing in opposite directions, so the flow lives here
# once. By default the target rank is worked out from the member's current rank
# via the ladder, so it cannot be mistyped.
#
# Naming a role overrides that, for the cases one step cannot express - skipping
# a rank, say. It still has to be on the ladder and still has to be in the
# direction the command implies: a "promotion" to a lower rank is refused.
#
# Who started the vote is taken from the interaction rather than asked for, and
# stored as the poll's author_id. There is no label to name the vote any more -
# its poll_id (shown at the bottom of the posted embed) is the only handle it
# gets, generated automatically once the poll row exists.
#
# The vote is always Yes/No and single choice: "should this one thing happen" has
# no sensible multi-answer form. Each answer spells out the rank it leads to, so
# a voter does not have to hold the question in their head while looking at the
# buttons: "Yes - Cadet" against "No - stay Sergeant", each carrying that rank's
# icon.

import discord
from Functions import sql_poll
from . import poll_store, poll_view, rank_ladder


def Answers(Current_Label, Target_Label):
    """The two answers, each naming the rank it results in.

    Order matters: the first answer is the affirmative, and /pollgrant reads it
    as "the vote passed" when it wins.
    """
    return ["Yes - %s" % Target_Label, "No - stay %s" % Current_Label]


async def Start(SQL_Connection, SQL_Cursor, client, interaction, Direction, member, channel, hours, Role=None):
    Word = "Promote" if Direction == rank_ladder.PROMOTION else "Demote"
    Poll_Type = sql_poll.POLL_TYPE_PROMOTION if Direction == rank_ladder.PROMOTION else sql_poll.POLL_TYPE_DEMOTION

    if hours < 1 or hours > 768:
        await interaction.response.send_message("Duration must be 1 to 768 hours.", ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("Bots don't hold clan ranks.", ephemeral=True)
        return

    Guild = interaction.guild

    # Their rank now. Reading this does not depend on what channels they can see;
    # roles belong to guild membership.
    Current = rank_ladder.Current_Rank(SQL_Cursor, member)
    if Current is None:
        await interaction.response.send_message(
            "**%s** doesn't hold any rank on the ladder, so there is nothing to %s from.\n"
            "Give them a starting rank first." % (member.display_name, Word.lower()),
            ephemeral=True)
        return

    # One step along the ladder, unless a specific rank was named
    if Role is not None:
        Target = Role
        Problem = rank_ladder.Validate_Target(SQL_Cursor, Current, Target, Direction)
    else:
        Target, Problem = rank_ladder.Step(SQL_Cursor, Guild, Current, Direction)
    if Problem:
        await interaction.response.send_message(Problem, ephemeral=True)
        return

    # Each rank has a matching emote; show it so the vote reads at a glance.
    Current_Icon = rank_ladder.Icon(Guild, Current.name)
    Target_Icon = rank_ladder.Icon(Guild, Target.name)
    Question = "%s %s from %s to %s?" % (
        Word, member.display_name,
        rank_ladder.With_Icon(Current_Icon, Current.name),
        rank_ladder.With_Icon(Target_Icon, Target.name))

    Answer_List = Answers(rank_ladder.With_Icon(Current_Icon, Current.name),
                          rank_ladder.With_Icon(Target_Icon, Target.name))

    Current_Rank_Id = rank_ladder.Rank_Id_For(SQL_Cursor, Current.id)
    Target_Rank_Id = rank_ladder.Rank_Id_For(SQL_Cursor, Target.id)

    Record = poll_store.Create(
        SQL_Connection, SQL_Cursor, channel.id, interaction.user.id, Question, Answer_List,
        False, hours, Poll_Type=Poll_Type, Subject_Id=member.id,
        Promotion_Rank_Id_Current=Current_Rank_Id, Promotion_Rank_Id_New=Target_Rank_Id)

    try:
        Message = await channel.send(
            embed=poll_view.Build_Embed(Record),
            view=poll_view.Poll_Buttons(SQL_Connection, SQL_Cursor, Record["poll_id"], Answer_List))
    except discord.Forbidden:
        await interaction.response.send_message(
            "I'm missing permissions in %s. I need 'View Channel' and 'Send Messages' there."
            % channel.mention, ephemeral=True)
        return

    poll_store.Attach_Message(SQL_Connection, SQL_Cursor, Record["poll_id"], Message.id)

    Kind_Label = "Promotion" if Direction == rank_ladder.PROMOTION else "Demotion"
    Chosen_Note = " (chosen, not the next rank on the ladder)" if Role is not None else ""
    Key = poll_store.Poll_Key_Encode(Record["poll_id"])
    await interaction.response.send_message(
        "%s\n%s vote posted in %s.\n**%s**: %s  ->  %s%s\n"
        "Close it with `/pollend poll_id:%s`, then apply it with `/pollgrant poll_id:%s`\n%s"
        % (poll_view.Reference(Record), Kind_Label, channel.mention,
           member.display_name,
           rank_ladder.With_Icon(Current_Icon, Current.name),
           rank_ladder.With_Icon(Target_Icon, Target.name),
           Chosen_Note, Key, Key, Message.jump_url),
        ephemeral=True)
