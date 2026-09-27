# The clan's rank progression - backed by SQL.
#
# Everything else asks this module four questions:
#
#   Current_Rank(SQL_Cursor, member)                  -> the rank they hold now, as a discord.Role
#   Step(SQL_Cursor, guild, current, direction)        -> the rank one place up or down
#   Validate_Target(SQL_Cursor, current, target, dir)  -> is this hand-picked target sensible
#   Icon(SQL_Cursor, discord_role_id)                  -> the rank's emote markup, for display
#
# The ranks live in SQL: discord_promotion_ranks links a discord_role_id to a
# promotion_rank_id, and discord_roles supplies that role's name.
# promotion_rank_id 0 ("not in clan") is not a rank - nothing is promoted onto
# it or demoted off it.
#
# THE PATH BETWEEN RANKS IS THE DATA'S, NOT THE CODE'S. Each rank's
# promotion_rank_id_progression names the rank a promotion leads to, and the
# code follows it without special cases:
#   - Promoting goes to the current rank's progression. A rank whose progression
#     points at itself (or at nothing) has no further promotion.
#   - Demoting goes to the rank whose progression points at the current rank -
#     the progression followed backwards. A rank nothing points at has no
#     default demotion.
#   - A hand-picked target must lie on that path: a promotion target must be
#     reachable by following progressions up from the current rank, and a
#     demotion target must be a rank whose progressions lead up to the current
#     one. Skipping ranks along the path is fine; ranks off it are refused.
# So with the default data Colonel promotes to Trialist (6 -> 8), and Astral,
# which points only at itself and which nothing points at, is never voted onto
# or off. promotion_rank_id's own order only decides which rank counts as a
# member's current one when they hold several (the highest wins).
#
# Icons are looked up live against the guild's current emoji list, matched by
# the rank's name - the same as before this migration. Everywhere an icon is
# needed, the caller already holds a live discord.Role (building a vote's
# question/answers in Commands/promotions.py, or the grant messages in
# Commands/promotions.py and Commands/polls.py), so
# there's no need to store discord_role_icon at all: a renamed rank or a
# changed emoji is picked up immediately, with nothing to keep in sync.

from Functions import sql_poll

# Direction of a vote. The values are only identifiers.
PROMOTION = -1
DEMOTION = +1


def Ladder_Get(SQL_Cursor):
    """Every rank, highest promotion_rank_id first: [{promotion_rank_id,
    discord_role_id, discord_role_name, promotion_rank_id_progression}, ...].
    No icon here - see Icon()/Rank_Emoji() for that, looked up live against the
    guild rather than stored."""
    return sql_poll.Promotion_Rank_Ladder_Get(SQL_Cursor)


def _Index_Of(Ladder, Discord_Role_Id):
    for i, Rank in enumerate(Ladder):
        if Rank["discord_role_id"] == Discord_Role_Id:
            return i
    return None


def _Rank_Of_Role(Ladder, Discord_Role_Id):
    """The ladder entry a role maps to, or None."""
    i = _Index_Of(Ladder, Discord_Role_Id)
    return Ladder[i] if i is not None else None


def _Next(Ranks, Rank_Id):
    """The rank a promotion from Rank_Id leads to, or None if its progression
    points at itself, at nothing, or at a rank that isn't a vote rank."""
    Rank = Ranks.get(Rank_Id)
    if Rank is None:
        return None
    Next_Id = Rank.get("promotion_rank_id_progression")
    if Next_Id is None or Next_Id == Rank_Id or Next_Id not in Ranks:
        return None
    return Ranks[Next_Id]


def _Previous(Ranks, Rank_Id):
    """Every rank whose progression leads to Rank_Id (itself excluded)."""
    return [R for Id, R in Ranks.items()
            if Id != Rank_Id and R.get("promotion_rank_id_progression") == Rank_Id]


def _Path_Up(Ranks, Rank_Id):
    """promotion_rank_ids reached by following progressions up from Rank_Id,
    nearest first, stopping at a rank with no further progression. Guarded
    against a loop in the data."""
    Path, Seen = [], {Rank_Id}
    Rank = _Next(Ranks, Rank_Id)
    while Rank is not None and Rank["promotion_rank_id"] not in Seen:
        Path.append(Rank["promotion_rank_id"])
        Seen.add(Rank["promotion_rank_id"])
        Rank = _Next(Ranks, Rank["promotion_rank_id"])
    return Path


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
    """The rank one step up or down from Current_Role, following
    promotion_rank_id_progression (see the top of this file).

    Returns (role, problem). Exactly one is ever set:
      (Role, None)      the target rank
      (None, "reason")  no target, with a sentence saying why
    """
    Ladder = Ladder_Get(SQL_Cursor)
    Ranks = {R["promotion_rank_id"]: R for R in Ladder}
    Current = _Rank_Of_Role(Ladder, Current_Role.id)
    if Current is None:
        return None, "**%s** is not a rank on the ladder." % Current_Role.name

    if Direction == PROMOTION:
        Target_Rank = _Next(Ranks, Current["promotion_rank_id"])
        if Target_Rank is None:
            return None, "**%s** has no further rank to promote to." % Current_Role.name
    else:
        Previous = _Previous(Ranks, Current["promotion_rank_id"])
        if not Previous:
            return None, "No rank promotes to **%s**, so there is nothing to demote to." % Current_Role.name
        if len(Previous) > 1:
            return None, ("More than one rank promotes to **%s** (%s), so pick the rank to demote to "
                          "with the role option." % (Current_Role.name,
                          ", ".join(R["discord_role_name"] for R in Previous)))
        Target_Rank = Previous[0]

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
    """Check a hand-picked target rank lies on the progression path in this direction.

    Returns a sentence explaining the problem, or None if the move is fine.
    Skipping ranks along the path is allowed; going the wrong way, or to a rank
    off the path, is not.
    """
    Ladder = Ladder_Get(SQL_Cursor)
    Ranks = {R["promotion_rank_id"]: R for R in Ladder}
    Current = _Rank_Of_Role(Ladder, Current_Role.id)
    Target = _Rank_Of_Role(Ladder, Target_Role.id)

    if Target is None:
        return ("**%s** is not a rank on the ladder, so it cannot be the target of a "
                "promotion or demotion vote." % Target_Role.name)
    if Current is not None and Target["promotion_rank_id"] == Current["promotion_rank_id"]:
        return "**%s** is the rank they already hold." % Target_Role.name

    Current_Id = Current["promotion_rank_id"] if Current else None
    Target_Id = Target["promotion_rank_id"]
    Up_From_Current = _Path_Up(Ranks, Current_Id) if Current_Id is not None else []
    Up_From_Target = _Path_Up(Ranks, Target_Id)
    if Direction == PROMOTION:
        if Target_Id in Up_From_Current:
            return None
        if Current_Id in Up_From_Target:
            return ("**%s** is below **%s** on the ladder, so that would be a demotion. "
                    "Use `/startdemotionvote` instead." % (Target_Role.name, Current_Role.name))
        return ("**%s** isn't on the promotion path from **%s**, so it can't be voted onto."
                % (Target_Role.name, Current_Role.name))
    if Current_Id in Up_From_Target:
        return None
    if Target_Id in Up_From_Current:
        return ("**%s** is above **%s** on the ladder, so that would be a promotion. "
                "Use `/startpromotionvote` instead." % (Target_Role.name, Current_Role.name))
    return ("**%s** isn't on the promotion path below **%s**, so it can't be demoted to."
            % (Target_Role.name, Current_Role.name))


def Describe(SQL_Cursor, Guild):
    """Every rank and where a promotion from it leads, marking anything the server
    is missing. Used at start-up."""
    Ladder = Ladder_Get(SQL_Cursor)
    Ranks = {R["promotion_rank_id"]: R for R in Ladder}
    Lines = []
    for Rank in sorted(Ladder, key=lambda R: R["promotion_rank_id"]):
        Found = Find_Role(Guild, Rank["discord_role_id"]) is not None
        Next = _Next(Ranks, Rank["promotion_rank_id"])
        Lines.append("  %2d. %-14s -> %-14s %s" % (
            Rank["promotion_rank_id"], Rank["discord_role_name"],
            Next["discord_role_name"] if Next else "(no further rank)",
            "" if Found else "<- NO ROLE WITH THIS ID"))
    return "\n".join(Lines)
