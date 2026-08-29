# Turning voters into guild members, and checking a role can actually be given.

async def Resolve_Member(Guild, User_Id):
    """A vote stores only a user id; role changes need a Member. Cache first, API second."""
    Member = Guild.get_member(User_Id)
    if Member is not None:
        return Member
    try:
        return await Guild.fetch_member(User_Id)   # works without the members intent
    except Exception:
        return None                                 # left the server

def Role_Blocker(Guild, *Roles):
    """Explain why the bot cannot change one of these roles, or None if it can.

    Takes several roles because a rank change removes one and adds another, and
    both sides need the same permission and hierarchy checks.
    """
    Me = Guild.me
    if not Me.guild_permissions.manage_roles:
        return "I don't have the 'Manage Roles' permission in this server."
    for Role in Roles:
        if Role is None:
            continue
        if Role.is_default():
            return "@everyone isn't a grantable role."
        if Role.managed:
            return "**%s** is managed by an integration, so nobody can assign it manually." % Role.name
        if Role >= Me.top_role:
            return ("**%s** sits above my own highest role (**%s**), so I can't change it. "
                    "Drag my role above it in Server Settings > Roles." % (Role.name, Me.top_role.name))
    return None
