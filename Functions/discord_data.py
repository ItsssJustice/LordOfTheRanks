#Fetch all roles in a guild
async def Roles_Get(client: discord.Client, guild_id: int) -> list[dict]:
    Guild = client.get_guild(int(guild_id))
    Guild_Roles = await Guild.fetch_roles()
    Role_Data = []
    for Role in Guild_Roles:
        Role_Data.append({
            "id": Role.id,
            "name": Role.name,
            "permissions": [perm for perm, value in Role.permissions if value]
        })
    #print(dir(Guild_Roles))
    return Role_Data

#Display all role information for all guild members
def Roles_Display(Role_List:  list[dict]) -> None:
    for Role in Role_List:
        print(f"{Role['id']} - {Role['name']}")
        if Role['permissions']:
            print(f"Permissions: {', '.join(Role['permissions'])}")
        else:
            print("Permissions: none")

# Gather information on all guild members
def Members_Get(client, guild_id):
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

#Display all member information for all guild members
def Members_Display(Member_List)  -> None:
    for member in Member_List:
        print(f"{member['id']} - {member['name_user']} - {member['discriminator']} - {member['name_global']} - {member['name_display']} - {member['name_nick']} - {member['roles']} - {member['perms']} - {member['bot']}")