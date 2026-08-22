# Gather information on all guild members
def Get(client, guild_id):
    members = {}
    Guild = client.get_guild(int(guild_id))
    for member in Guild.members:
        if(not member.bot):
            members[member.id] = {
                "id": member.id,
                "name_user": member.name,
                "discriminator": member.discriminator,
                "name_global": member.global_name,
                "name_display": member.display_name,
                "name_nick": member.nick,
                "roles": member.roles,
                "perms": member.guild_permissions,
                "bot": member.bot,
                "member": member
            }
    #print(dir(member))
    return list(members.values())

#Display all core information for all guild members
def Display(Member_List)  -> None:
    for member in Member_List:
        print(f"{member['id']} - {member['name_user']} - {member['discriminator']} - {member['name_global']} - {member['name_display']} - {member['name_nick']} - {member['roles']} - {member['perms']} - {member['bot']}")