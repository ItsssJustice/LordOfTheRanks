# The clan's rank progression - backed by SQL.
#
# Everything else asks this module four questions:
#
#   Current_Rank(SQL_Cursor, member)                  -> the rank they hold now, as a discord.Role
#   Step(SQL_Cursor, guild, current, direction)        -> the rank one place up or down
#   Validate_Target(SQL_Cursor, current, target, dir)  -> is this hand-picked target sensible
#   Icon(SQL_Cursor, discord_role_id)                  -> the rank's emote markup, for display
#
# The ladder and its role mapping now live in SQL: discord_promotion_ranks
# links a discord_role_id to a promotion_rank_id, and discord_roles supplies
# that role's name and icon. promotion_rank_id 0 ("not in clan") is not a rank
# on the ladder - nothing is promoted onto it or demoted off it.
#
# See sql_poll.Promotion_Rank_Ladder_Get for why the ladder is ordered by
# promotion_rank_id itself and NOT by promotion_rank_id_progression: the
# progression column is the automatic points-promotion system's own "next
# rank" pointer, and does not reproduce this ladder faithfully (it skips
# Astral, and ties General with Deputy Owner).
#
# Icons are looked up live against the guild's current emoji list, matched by
# the rank's name - the same as before this migration. Everywhere an icon is
# needed, the caller already holds a live discord.Role (building a vote's
# question/answers in rank_vote.py, or the grant message in Poll_Grant.py), so
# there's no need to store discord_role_icon at all: a renamed rank or a
# changed emoji is picked up immediately, with nothing to keep in sync.

from Functions import sql_poll

# Index 0 is the top of the ladder, so promoting moves the index down.
PROMOTION = -1
DEMOTION = +1


def Ladder_Get(SQL_Cursor):
    """The ladder, highest rank first: [{promotion_rank_id, discord_role_id,
    discord_role_name}, ...]. No icon here - see Icon()/Rank_Emoji() for that,
    looked up live against the guild rather than stored."""
    return sql_poll.Promotion_Rank_Ladder_Get(SQL_Cursor)


def _Index_Of(Ladder, Discord_Role_Id):
    for i, Rank in enumerate(Ladder):
        if Rank["discord_role_id"] == Discord_Role_Id:
            return i
    return None


def Rank_Id_For(SQL_Cursor, Discord_Role_Id):
    """The promotion_rank_id a role maps to, or None if it isn't on the ladder."""
    return sql_poll.Promotion_Rank_For_Role(SQL_Cursor, Discord_Role_Id)


def Find_Role(Guild, Discord_Role_Id):
    """The guild's live role for a ladder entry, or None if the server has no such role."""
    return Guild.get_role(Discord_Role_Id) if Discord_Role_Id else None


def Find_Role_By_Name(Guild, Name):
    """Fallback lookup by name, for when a ladder entry's discord_role_id has
    drifted out of date (the role was deleted and remade, say)."""
    if not Name:
        return None
    Wanted = Name.lower()
    for Role in Guild.roles:
        if Role.name.lower() == Wanted:
            return Role
    return None


def Missing_Roles(SQL_Cursor, Guild):
    """Ladder entries whose discord_role_id no longer exists in this server. Empty list means all present."""
    return [Rank["discord_role_name"] for Rank in Ladder_Get(SQL_Cursor)
            if Find_Role(Guild, Rank["discord_role_id"]) is None]


def Current_Rank(SQL_Cursor, Member):
    """The member's rank: the highest ladder role they hold live, or None if they hold none.

    Members should only ever hold one, but if somehow they hold several the
    highest wins, which is the safe reading.
    """
    Ladder = Ladder_Get(SQL_Cursor)
    Best_Index, Best_Role_Id = None, None
    for Role in Member.roles:
        i = _Index_Of(Ladder, Role.id)
        if i is not None and (Best_Index is None or i < Best_Index):
            Best_Index, Best_Role_Id = i, Role.id
    if Best_Role_Id is None:
        return None
    return Member.guild.get_role(Best_Role_Id)


def Step(SQL_Cursor, Guild, Current_Role, Direction):
    """The rank one step up or down from Current_Role.

    Returns (role, problem). Exactly one is ever set:
      (Role, None)      the target rank
      (None, "reason")  no target, with a sentence saying why
    """
    Ladder = Ladder_Get(SQL_Cursor)
    Index = _Index_Of(Ladder, Current_Role.id)
    if Index is None:
        return None, "**%s** is not a rank on the ladder." % Current_Role.name

    Target_Index = Index + Direction
    if Target_Index < 0:
        return None, "**%s** is the highest rank, so there is nothing to promote to." % Current_Role.name
    if Target_Index >= len(Ladder):
        return None, "**%s** is the lowest rank, so there is nothing to demote to." % Current_Role.name

    Target_Rank = Ladder[Target_Index]
    Target_Role = Find_Role(Guild, Target_Rank["discord_role_id"])
    if Target_Role is None:
        return None, ("The next rank would be **%s**, but this server has no role with that id (%s). "
                      "Check discord_promotion_ranks against Server Settings > Roles."
                      % (Target_Rank["discord_role_name"], Target_Rank["discord_role_id"]))
    return Target_Role, None


def _Normalise(Name):
    """Lowercase, letters and digits only, so "Deputy Owner" matches :deputyowner:
    and :deputy_owner: alike."""
    return "".join(c for c in (Name or "").lower() if c.isalnum())


def Rank_Emoji(Guild, Rank_Name):
    """The server emoji named after a rank, or None if there is not one.

    Each rank has a matching emote, so a vote can show the icon rather than only
    the word. Matching is on the name, since the emoji ids differ per server.
    """
    Wanted = _Normalise(Rank_Name)
    for Emoji in Guild.emojis:
        if _Normalise(Emoji.name) == Wanted:
            return Emoji
    return None


def Icon(Guild, Rank_Name):
    """The rank's emoji as markup, or "" when the server has no such emote."""
    Emoji = Rank_Emoji(Guild, Rank_Name)
    return str(Emoji) if Emoji else ""


def With_Icon(Icon_Markup, Name):
    """"<:recruit:1> Recruit", or just "Recruit" when there is no icon."""
    return ("%s %s" % (Icon_Markup, Name)) if Icon_Markup else Name


def Validate_Target(SQL_Cursor, Current_Role, Target_Role, Direction):
    """Check a hand-picked target rank makes sense for this direction.

    Returns a sentence explaining the problem, or None if the move is fine.
    Skipping steps is allowed; going the wrong way is not.
    """
    Ladder = Ladder_Get(SQL_Cursor)
    Current_Index = _Index_Of(Ladder, Current_Role.id)
    Target_Index = _Index_Of(Ladder, Target_Role.id)

    if Target_Index is None:
        return ("**%s** is not a rank on the ladder, so it cannot be the target of a "
                "promotion or demotion vote." % Target_Role.name)
    if Target_Index == Current_Index:
        return "**%s** is the rank they already hold." % Target_Role.name

    Moving_Up = Target_Index < Current_Index
    if Direction == PROMOTION and not Moving_Up:
        return ("**%s** is below **%s** on the ladder, so that would be a demotion. "
                "Use `/startdemotionvote` instead." % (Target_Role.name, Current_Role.name))
    if Direction == DEMOTION and Moving_Up:
        return ("**%s** is above **%s** on the ladder, so that would be a promotion. "
                "Use `/startpromotionvote` instead." % (Target_Role.name, Current_Role.name))
    return None


def Describe(SQL_Cursor, Guild):
    """Ladder as text, marking anything the server is missing. Used at start-up."""
    Ladder = Ladder_Get(SQL_Cursor)
    Lines = []
    for i, Rank in enumerate(Ladder):
        Found = Find_Role(Guild, Rank["discord_role_id"]) is not None
        Lines.append("  %2d. %-14s %s" % (i + 1, Rank["discord_role_name"],
                                          "" if Found else "<- NO ROLE WITH THIS ID"))
    return "\n".join(Lines)
