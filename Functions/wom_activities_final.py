import asyncio
import argparse
import json
import wom


GROUP_ID = 3027
LIMIT = 50


async def get_data():
    client = wom.Client()
    await client.start()

    try:
        # get latest 50 activities
        result = await client.groups.get_activity(
            GROUP_ID,
            limit=LIMIT
        )

        if not result.is_ok:
            print("Failed to retrieve group activities:")
            print(result)
            return None

	# Original output here in results.unwrap()
        activities = result.unwrap()

        # filter and restructure JSON
        output = {
            "activities": [
                {
                    "group_id": activity.group_id,
                    "player_id": activity.player_id,
                    "display_name": activity.player.display_name,
                    "type": activity.type.value,
                    "role": activity.role.value if activity.role else None,
                    "created_at": activity.created_at.isoformat()
                }
                for activity in activities
                if activity.type.value in (
                    "joined",
                    "left",
                    "changed_role"
                )
            ]
        }

        return output

    finally:
        await client.close()


def print_pretty(data):
    activities = data["activities"]

    print()
    print(f"Group activities: {len(activities)}")
    print()

    print(
        f"{'Type':<15}"
        f"{'Player ID':<12}"
        f"{'Display Name':<25}"
        f"{'Role':<15}"
        f"{'Created At':<30}"
    )

    print("-" * 97)

    for activity in activities:
        print(
            f"{activity['type']:<15}"
            f"{activity['player_id']:<12}"
            f"{activity['display_name']:<25}"
            f"{str(activity['role']):<15}"
            f"{activity['created_at']:<30}"
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

    if data is None:
        return

    if args.pretty:
        print_pretty(data)
    else:
        print(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
