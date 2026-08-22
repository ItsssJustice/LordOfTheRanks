#Fetch all roles in a guild
async def Get(client: discord.Client, guild_id: int) -> list[dict]:
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

def Display(Role_List:  list[dict]) -> None:
    for Role in Role_List:
        print(f"{Role['id']} - {Role['name']}")
        if Role['permissions']:
            print(f"Permissions: {', '.join(Role['permissions'])}")
        else:
            print("Permissions: none")