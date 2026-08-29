# The clan's rank progression.
#
# THIS MODULE IS THE SWAPPABLE PART. Everything else asks it four questions:
#
#   Current_Rank(member)                -> the rank they hold now
#   Step(guild, current, direction)     -> the rank one place up or down
#   Validate_Target(current, target, d) -> is this hand-picked target sensible
#   Icon(guild, rank_name)              -> the rank's emote, for display
#
# Nothing outside this file knows how the order is decided, so replacing the
# list below with a lookup against the members table swaps the source without
# touching a single command. That is the intended end state: the ladder and its
# role mapping live in SQL, and this file becomes the adapter in front of it.
#
# Until then the order is written down here. Discord gives roles a `position`,
# but that ordering mixes ranks in with colour roles, ping roles and bot roles,
# so it cannot be used to work out what the next rank is.
#
# Highest first. Roles are matched by name, case-insensitively, so these must
# match the role names in the server.

LADDER = [
    "Owner",
    "Deputy Owner",
    "General",
    "Captain",
    "Lieutenant",
    "Trialist",
    "Astral",
    "Colonel",
    "Cadet",
    "Sergeant",
    "Corporal",
    "Recruit",
    "Infantry",
]

# Index 0 is the top of the ladder, so promoting moves the index down.
PROMOTION = -1
DEMOTION = +1

def Index_Of(Role_Name):
    """Where a role sits on the ladder, or None if it is not a rank at all."""
    Wanted = (Role_Name or "").strip().lower()
    for i, Name in enumerate(LADDER):
        if Name.lower() == Wanted:
            return i
    return None

def Find_Role(Guild, Ladder_Name):
    """The guild's role for a ladder entry, or None if the server has no such role."""
    Wanted = Ladder_Name.lower()
    for Role in Guild.roles:
        if Role.name.lower() == Wanted:
            return Role
    return None

def Missing_Roles(Guild):
    """Ladder entries that do not exist in this server. Empty list means all present."""
    return [Name for Name in LADDER if Find_Role(Guild, Name) is None]

def Current_Rank(Member):
    """The member's rank: the highest ladder role they hold, or None if they hold none.

    Members should only ever hold one, but if somehow they hold several the
    highest wins, which is the safe reading.
    """
    Best_Index, Best_Role = None, None
    for Role in Member.roles:
        i = Index_Of(Role.name)
        if i is not None and (Best_Index is None or i < Best_Index):
            Best_Index, Best_Role = i, Role
    return Best_Role

def Step(Guild, Current_Role, Direction):
    """The rank one step up or down from Current_Role.

    Returns (role, problem). Exactly one is ever set:
      (Role, None)      the target rank
      (None, "reason")  no target, with a sentence saying why
    """
    Index = Index_Of(Current_Role.name)
    if Index is None:
        return None, "**%s** is not a rank on the ladder." % Current_Role.name

    Target_Index = Index + Direction
    if Target_Index < 0:
        return None, "**%s** is the highest rank, so there is nothing to promote to." % Current_Role.name
    if Target_Index >= len(LADDER):
        return None, "**%s** is the lowest rank, so there is nothing to demote to." % Current_Role.name

    Target_Name = LADDER[Target_Index]
    Target_Role = Find_Role(Guild, Target_Name)
    if Target_Role is None:
        return None, ("The next rank would be **%s**, but this server has no role by that name. "
                      "Check the names in Functions/rank_ladder.py against Server Settings > Roles."
                      % Target_Name)
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

def Validate_Target(Current_Role, Target_Role, Direction):
    """Check a hand-picked target rank makes sense for this direction.

    Returns a sentence explaining the problem, or None if the move is fine.
    Skipping steps is allowed; going the wrong way is not.
    """
    Current_Index = Index_Of(Current_Role.name)
    Target_Index = Index_Of(Target_Role.name)

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

def Describe(Guild):
    """Ladder as text, marking anything the server is missing. Used at start-up."""
    Lines = []
    for i, Name in enumerate(LADDER):
        Found = Find_Role(Guild, Name) is not None
        Lines.append("  %2d. %-14s %s" % (i + 1, Name, "" if Found else "<- NO ROLE WITH THIS NAME"))
    return "\n".join(Lines)
