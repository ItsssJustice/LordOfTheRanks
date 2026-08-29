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
# stored with it, so the record says who proposed the change.
#
# The vote is always Yes/No and single choice: "should this one thing happen" has
# no sensible multi-answer form. Each answer spells out the rank it leads to, so
# a voter does not have to hold the question in their head while looking at the
# buttons: "Yes - Cadet" against "No - stay Sergeant", each carrying that rank's
# icon.

import discord
from . import poll_store, poll_view, rank_ladder

def Answers(Current_Label, Target_Label):
    """The two answers, each naming the rank it results in.

    Order matters: the first answer is the affirmative, and /pollgrant reads it
    as "the vote passed" when it wins.
    """
    return ["Yes - %s" % Target_Label, "No - stay %s" % Current_Label]

async def Start(client, interaction, Direction, label, member, channel, hours, Role=None):
    Word = "Promote" if Direction == rank_ladder.PROMOTION else "Demote"
    Kind = "promotion" if Direction == rank_ladder.PROMOTION else "demotion"

    if len(label) > poll_store.LABEL_LIMIT:
        await interaction.response.send_message(
            "Label must be %d characters or fewer, that one is %d.\nA custom emoji counts for "
            "about thirty characters on its own, because discord sends it to me as "
            "`<:name:1234567890123456789>`."
            % (poll_store.LABEL_LIMIT, len(label)), ephemeral=True)
        return
    if hours < 1 or hours > 768:
        await interaction.response.send_message("Duration must be 1 to 768 hours.", ephemeral=True)
        return
    if poll_store.Find(label):
        await interaction.response.send_message(
            "The label '% s' is already in use." % label, ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("Bots don't hold clan ranks.", ephemeral=True)
        return

    Guild = interaction.guild

    # Their rank now. Reading this does not depend on what channels they can see;
    # roles belong to guild membership.
    Current = rank_ladder.Current_Rank(member)
    if Current is None:
        await interaction.response.send_message(
            "**%s** doesn't hold any rank on the ladder, so there is nothing to %s from.\n"
            "Give them a starting rank first." % (member.display_name, Word.lower()),
            ephemeral=True)
        return

    # One step along the ladder, unless a specific rank was named
    if Role is not None:
        Target = Role
        Problem = rank_ladder.Validate_Target(Current, Target, Direction)
    else:
        Target, Problem = rank_ladder.Step(Guild, Current, Direction)
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

    Record = poll_store.Create(
        label, interaction.guild_id, channel.id, Question, Answer_List,
        False, hours, Extra={
            "kind": Kind,
            "subject_id": member.id,
            "subject_name": member.display_name,
            "role_id": Target.id,
            "role_name": Target.name,
            "from_role_id": Current.id,
            "from_role_name": Current.name,
            "role_icon": Target_Icon,
            "from_role_icon": Current_Icon,
            "started_by_id": interaction.user.id,
            "started_by_name": interaction.user.display_name,
        })

    try:
        Message = await channel.send(embed=poll_view.Build_Embed(Record),
                                     view=poll_view.Poll_Buttons(Record["key"], Answer_List))
    except discord.Forbidden:
        await interaction.response.send_message(
            "I'm missing permissions in %s. I need 'View Channel' and 'Send Messages' there."
            % channel.mention, ephemeral=True)
        return

    poll_store.Attach_Message(label, Message.id)

    Chosen_Note = " (chosen, not the next rank on the ladder)" if Role is not None else ""
    await interaction.response.send_message(
        "%s\n%s vote posted in %s.\n**%s**: %s  ->  %s%s\n"
        "Close it with `/pollend label:%s`, then apply it with `/pollgrant label:%s`\n%s"
        % (poll_view.Reference(Record), Kind.capitalize(), channel.mention,
           member.display_name,
           rank_ladder.With_Icon(Current_Icon, Current.name),
           rank_ladder.With_Icon(Target_Icon, Target.name),
           Chosen_Note, label, label, Message.jump_url),
        ephemeral=True)
