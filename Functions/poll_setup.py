# Everything the rank vote commands need doing once the bot is connected.
#
# This lives here rather than in the bot's own file so that adding rank votes
# touches the core in one place: a single awaited call from on_ready. Nothing
# else about the bot has to know these commands exist.
#
# NOTE: as of this SQL migration, the call to On_Ready in LordOfTheRanks.py's
# on_ready() is still commented out (it was already commented out before this
# change, so button re-registration after a restart and the expired-poll
# closer loop are both still dormant). Uncomment it there, passing
# SQL_Connection and SQL_Cursor, to actually run this.

import asyncio
from . import poll_store, poll_view, rank_ladder

async def On_Ready(SQL_Connection, SQL_Cursor, client, Guild_Id):
    """Call once from on_ready.

    Re-registers the buttons on votes that are still open, reports the rank
    ladder against the server's real roles, and starts watching for votes whose
    time is up.
    """
    # A vote's buttons only keep working across a restart if their view is
    # re-registered by custom_id, so do that for every vote still open.
    Open_Polls = poll_store.Open_Records(SQL_Cursor)
    for Record in Open_Polls:
        client.add_view(poll_view.Poll_Buttons(SQL_Connection, SQL_Cursor, Record["poll_id"], Record["answers"]))
    print("Re-registered % d open poll(s)" % len(Open_Polls))

    Report_Ladder(SQL_Cursor, client, Guild_Id)

    # Their duration is enforced here rather than by discord, since this bot
    # holds the votes
    client.loop.create_task(Close_Expired_Polls(SQL_Connection, SQL_Cursor, client))

def Report_Ladder(SQL_Cursor, client, Guild_Id):
    """Print the ladder against the server's roles, so a renamed or missing rank
    shows up at start-up rather than halfway through a vote."""
    Guild = client.get_guild(int(Guild_Id)) if str(Guild_Id).isdigit() else None
    if Guild is None:
        print("Could not read guild % s, skipping the rank ladder check" % Guild_Id)
        return
    Missing = rank_ladder.Missing_Roles(SQL_Cursor, Guild)
    print("Rank ladder (highest first):")
    print(rank_ladder.Describe(SQL_Cursor, Guild))
    if Missing:
        print("WARNING: % d ladder rank(s) have no matching role: % s"
              % (len(Missing), ", ".join(Missing)))
        print("Votes towards those will fail. Check discord_promotion_ranks' discord_role_id "
              "values against Server Settings > Roles.")

async def Close_Expired_Polls(SQL_Connection, SQL_Cursor, client):
    """Publish the result of any vote whose deadline has passed."""
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            for Record in poll_store.All_Records(SQL_Cursor):
                if Record.get("closed") or not poll_store.Is_Closed(Record):
                    continue
                print("Poll '% s' reached its deadline, closing" % poll_store.Poll_Key_Encode(Record["poll_id"]))
                Closed_Record = poll_store.Close(SQL_Connection, SQL_Cursor, Record["poll_id"])
                await poll_view.Refresh_Message(SQL_Connection, SQL_Cursor, client, Closed_Record)
        except Exception as Error:
            print("Poll closer hit an error: % r" % Error)
        await asyncio.sleep(60)
