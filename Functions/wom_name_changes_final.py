import asyncio
import argparse
import json
import wom


GROUP_ID = 3027
LIMIT = 50


async def get_data():
    client = wom.Client()

    try:
        await client.start()

        result = await client.groups.get_name_changes(
            GROUP_ID,
            limit=LIMIT
        )

        if not result.is_ok:
            raise Exception(
                f"Failed to retrieve name changes: {result}"
            )
	# original response here
        changes = result.unwrap()

	#create JSON structure
        data = {
            "nameChanges": [
                {
                    "id": change.id,
                    "player_id": change.player_id,
                    "old_name": change.old_name,
                    "new_name": change.new_name,
                    "created_at": change.created_at.isoformat()
                }
                for change in changes
            ]
        }

        return data

    finally:
        await client.close()

# make --pretty flag possible
def print_pretty(data):
    changes = data["nameChanges"]

    print()
    print(f"Latest {len(changes)} name changes")
    print()

    print(
        f"{'ID':<10}"
        f"{'Player ID':<12}"
        f"{'Old Name':<25}"
        f"{'New Name':<25}"
        f"{'Created At':<30}"
    )

    print("-" * 102)

    for change in changes:
        print(
            f"{change['id']:<10}"
            f"{change['player_id']:<12}"
            f"{change['old_name']:<25}"
            f"{change['new_name']:<25}"
            f"{change['created_at']:<30}"
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
