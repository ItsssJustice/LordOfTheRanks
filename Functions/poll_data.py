# Structured access to a poll's results, for code rather than for chat.
#
# /pollresults formats a poll into a message for a human. This module hands the
# same information back as plain Python objects so other code can act on it --
# granting roles, awarding points, whatever.
#
# The one thing to be careful about: Discord's docs warn that while a poll is
# still running the counts "may not be perfectly accurate", because tallying at
# scale is done lazily. is_finalised() only becomes True after the poll ends and
# Discord's background job has done a precise count. So anything that hands out
# ranks should wait for a finalised poll -- see Require_Closed in Poll_Grant.py.

async def Fetch(client, Record, With_Voters=False):
    """Read a stored poll back off Discord.

    Returns None if the poll can no longer be found, otherwise a dict:
        question  str
        closed    bool   -- results are final and precisely counted
        total     int
        message   discord.Message
        guild     discord.Guild
        answers   list of {id, text, count, voters}
                  voters is a list of discord.User, empty unless With_Voters
    """
    Channel = client.get_channel(Record["channel_id"])
    if Channel is None:
        Channel = await client.fetch_channel(Record["channel_id"])

    Message = await Channel.fetch_message(Record["message_id"])
    Poll = Message.poll
    if Poll is None:
        return None

    Answers = []
    for Answer in Poll.answers:
        Voters = []
        if With_Voters:
            # voters() pages the API for us (100 per request), so just iterate
            Voters = [User async for User in Answer.voters()]
        Answers.append({
            "id": Answer.id,
            "text": Answer.text,
            "count": Answer.vote_count,
            "voters": Voters,
        })

    return {
        "question": Poll.question,
        "closed": Poll.is_finalised(),
        "total": Poll.total_votes,
        "message": Message,
        "guild": Message.guild,
        "answers": Answers,
    }

async def Resolve_Member(Guild, User):
    """A voter arrives as a User; role changes need a Member. Cache first, API second."""
    Member = Guild.get_member(User.id)
    if Member is not None:
        return Member
    try:
        return await Guild.fetch_member(User.id)   # works without the members intent
    except Exception:
        return None                                 # left the server

def Role_Blocker(Guild, Role):
    """Return a human explanation if the bot cannot hand out this role, else None."""
    Me = Guild.me
    if not Me.guild_permissions.manage_roles:
        return "I don't have the 'Manage Roles' permission in this server."
    if Role.is_default():
        return "@everyone isn't a grantable role."
    if Role.managed:
        return "**%s** is managed by an integration, so nobody can assign it manually." % Role.name
    if Role >= Me.top_role:
        return ("**%s** sits above my own highest role (**%s**), so I can't assign it. "
                "Drag my role above it in Server Settings > Roles." % (Role.name, Me.top_role.name))
    return None
