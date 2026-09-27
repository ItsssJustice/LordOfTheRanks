# Everything the rank vote commands need doing once the bot is connected.
#
# This lives here rather than in the bot's own file so that adding rank votes
# touches the core in one place: a single awaited call from on_ready. Nothing
# else about the bot has to know these commands exist.
#
# The expired-poll closer also hands every poll it closes to On_Poll_Closed, a
# callback supplied by LordOfTheRanks.py (Commands/promotions.py's
# Promotion_On_Poll_Closed), which applies passed demotions and promotions onto
# automatic ranks. The grant code stays in the command file; this module only
# knows there is something to call. That makes this loop load-bearing, so it is
# started once only, even though discord fires on_ready again on reconnects.

import asyncio
from . import poll_store, poll_view, rank_ladder, poll_members, discord_connection

_Closer_Started = False

async def On_Ready(SQL_Connection, SQL_Cursor, client, Guild_Id, On_Poll_Closed=None):
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
    global _Closer_Started
    if not _Closer_Started:
        _Closer_Started = True
        client.loop.create_task(Close_Expired_Polls(SQL_Connection, SQL_Cursor, client, Guild_Id, On_Poll_Closed))

def Report_Ladder(SQL_Cursor, client, Guild_Id):
    """Print the ladder against the server's roles, so a renamed or missing rank
    shows up at start-up rather than halfway through a vote."""
    Guild = client.get_guild(int(Guild_Id)) if str(Guild_Id).isdigit() else None
    if Guild is None:
        print("Could not read guild % s, skipping the rank ladder check" % Guild_Id)
        return
    Missing = rank_ladder.Missing_Roles(SQL_Cursor, Guild)
    print("Rank ladder (each rank -> where a promotion leads):")
    print(rank_ladder.Describe(SQL_Cursor, Guild))
    if Missing:
        print("WARNING: % d ladder rank(s) have no matching role: % s"
              % (len(Missing), ", ".join(Missing)))
        print("Votes towards those will fail. Check discord_promotion_ranks' discord_role_id "
              "values against Server Settings > Roles.")
    # A bot can only give or remove roles below its own highest role, whatever its
    # permissions - so say at start-up which ranks it won't be able to apply
    Blocked = []
    for Rank in rank_ladder.Ladder_Get(SQL_Cursor):
        Role = rank_ladder.Find_Role(Guild, Rank["discord_role_id"])
        Reason = poll_members.Role_Blocker(Guild, Role) if Role is not None else None
        if Reason:
            Blocked.append(Reason)
    if Blocked:
        print("WARNING: %d rank(s) can't be assigned by the bot, so votes onto or off them "
              "won't apply:" % len(Blocked))
        for Reason in Blocked:
            print("  - " + Reason)

async def Close_Expired_Polls(SQL_Connection, SQL_Cursor, client, Guild_Id, On_Poll_Closed=None):
    """Publish the result of any vote whose deadline has passed, then pass it to
    On_Poll_Closed(client, Guild, Record) if one was given."""
    # Runs for the life of the process: if Discord drops and discord_connection
    # restarts the client, this waits for it to be ready again rather than ending.
    while True:
        await discord_connection.Wait_Until_Connected(client)
        try:
            for Record in poll_store.Expired_Unclosed_Records(SQL_Cursor):
                if Record.get("closed") or not poll_store.Is_Closed(Record):
                    continue
                print("Poll '% s' reached its deadline, closing" % poll_store.Poll_Key_Encode(Record["poll_id"]))
                Closed_Record = poll_store.Close(SQL_Connection, SQL_Cursor, Record["poll_id"])
                await poll_view.Refresh_Message(SQL_Connection, SQL_Cursor, client, Closed_Record)
                if On_Poll_Closed is not None:
                    await On_Poll_Closed(client, client.get_guild(int(Guild_Id)), Closed_Record)
        except Exception as Error:
            print("Poll closer hit an error: % r" % Error)
        await asyncio.sleep(60)
