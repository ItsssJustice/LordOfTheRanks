import asyncio
import argparse
import json
import wom


GROUP_ID = 3027


async def get_data():
    client = wom.Client()

    try:
        await client.start()

        result = await client.groups.get_details(GROUP_ID)

        if not result.is_ok:
            raise Exception(
                f"Failed to retrieve group details: {result}"
            )
	# original data here
        group = result.unwrap()

	# create new JSON structure
        data = {
            "groupData": {
                "id": group.id,
                "name": group.name,
                "member_count": group.member_count,
                "memberships": [
                    {
                        "player_id": membership.player_id,
                        "display_name": membership.player.display_name,
                        "role": membership.role.value,
                        "created_at": membership.created_at.isoformat()
                    }
                    for membership in group.memberships
                ]
            }
        }

        return data

    finally:
        await client.close()

# make --pretty flag possible for troubleshooting, can be removed in final
def print_pretty(data):
    group = data["groupData"]

    print()
    print(f"Group:        {group['name']}")
    print(f"ID:           {group['id']}")
    print(f"Member count: {group['member_count']}")
    print()

    print(
        f"{'Player ID':<12}"
        f"{'Display Name':<25}"
        f"{'Role':<15}"
        f"{'Joined':<30}"
    )

    print("-" * 82)

    for membership in group["memberships"]:
        print(
            f"{membership['player_id']:<12}"
            f"{membership['display_name']:<25}"
            f"{membership['role']:<15}"
            f"{membership['created_at']:<30}"
        )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Display output as a readable table"
    )

    args = parser.parse_args()

    data = await get_data()

    if args.pretty:
        print_pretty(data)
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
