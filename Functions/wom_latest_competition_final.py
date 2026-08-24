import asyncio
import argparse
import json
import wom


GROUP_ID = 3027


async def get_data():
    client = wom.Client()

    try:
        await client.start()

        # get all competitions for group
        result = await client.groups.get_competitions(GROUP_ID)

        if not result.is_ok:
            raise Exception(f"Failed to retrieve competitions: {result}")

        competitions = result.unwrap()

        if not competitions:
            raise Exception("No competitions found.")

        # latest competition ordered on startdate
        latest = max(
            competitions,
            key=lambda c: c.starts_at
        )

        # get details from latest comp
        details_result = await client.competitions.get_details(
            latest.id
        )

        if not details_result.is_ok:
            raise Exception(
                f"Failed to retrieve competition details: "
                f"{details_result}"
            )

	# original call output
        details = details_result.unwrap()

        # filter for only participants with XP gained
        participants = sorted(
            (
                p for p in details.participations
                if p.progress.gained > 0
            ),
            key=lambda p: p.progress.gained,
            reverse=True
        )

	# create JSON structure
        data = {
            "competition": {
                "competition_id": details.id,
                "title": details.title,
                "starts_at": details.starts_at.isoformat(),
                "ends_at": details.ends_at.isoformat(),
                "metric": details.metric.value,
                "results": [
                    {
                        "player_id": participant.player_id,
                        "display_name": participant.player.display_name,
                        "gained": participant.progress.gained
                    }
                    for participant in participants
                ]
            }
        }

        return data

    finally:
        await client.close()

# make --pretty flag possible for troubleshooting purposes
def print_pretty(data):
    competition = data["competition"]

    print()
    print(f"Competition: {competition['title']}")
    print(f"ID:         {competition['competition_id']}")
    print(f"Starts at:  {competition['starts_at']}")
    print(f"Ends at:    {competition['ends_at']}")
    print(f"Metric:     {competition['metric']}")
    print()

    print(
        f"{'Rank':<8}"
        f"{'Player ID':<12}"
        f"{'Display Name':<25}"
        f"{'Gained':>12}"
    )

    print("-" * 57)

    for rank, result in enumerate(
        competition["results"],
        start=1
    ):
        print(
            f"{rank:<8}"
            f"{result['player_id']:<12}"
            f"{result['display_name']:<25}"
            f"{result['gained']:>12}"
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
