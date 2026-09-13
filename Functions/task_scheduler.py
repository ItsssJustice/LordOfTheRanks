import asyncio
import datetime
import math
from Functions import sql_task_scheduler
from Functions import sql_account_discord
from Functions import sql_account_osrs
from Functions import sql_account_link
from Functions import wom_data
from Functions import discord_data

# Fixed reference point every timing's grid is measured from. Any constant works as long as
# it never changes - Unix epoch is the obvious, restart-safe choice, since it needs no storage
# and is identical on every machine this ever runs on.
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

async def On_Ready(Command_Namespace):
    """Call once from on_ready. Runs every run_on_startup block immediately, once, regardless
    of where its own grid timing currently sits - then starts the regular grid-based loop.

    Takes the whole Command_Namespace dict rather than individual arguments, so any variable a
    scheduled block needs (client, SQL handles, guild/env ids, etc.) is available to it without
    every function in this file's call chain having to be updated whenever a new one is added
    to Command_Namespace.
    """
    await Scheduled_Tasks(Command_Namespace, Initial_Startup=True)
    Command_Namespace["DISCORD_CLIENT"].loop.create_task(Scheduled_Task_Loop(Command_Namespace))

async def Scheduled_Task_Loop(Command_Namespace):
    client = Command_Namespace["DISCORD_CLIENT"]
    SQL_Cursor = Command_Namespace["SQL_Cursor"]

    await client.wait_until_ready()
    while not client.is_closed():
        try:
            await Scheduled_Tasks(Command_Namespace)
        except Exception as Error:
            print("Scheduled : daily run hit an error: %r" % Error)

        # timing_id 1 / name "scheduler_loop" is this loop's own cadence, read fresh each pass
        # so interval_seconds can be changed in the table without a bot restart
        Loop_Timing = sql_task_scheduler.Timing_Get(SQL_Cursor, 1)
        Scheduled_Seconds = Loop_Timing["interval_seconds"] if Loop_Timing else 900
        await asyncio.sleep(Scheduled_Seconds)

async def Scheduled_Tasks(Command_Namespace, Initial_Startup=False):
    """Runs whichever bot_timings entries are due, or - when Initial_Startup is True - every
    entry with run_on_startup set, unconditionally.

    On a normal pass, each entry fires on its own fixed grid (see _Is_Due) rather than off
    "time since it last ran" - that's what keeps offset-related entries like
    promotion_votes_create/promotion_votes_action a constant distance apart forever, instead
    of that gap drifting as jitter accumulates on either side independently.

    On the startup pass, _Is_Due is deliberately bypassed - a fresh restart should not have to
    wait for its grid boundary just because update_time happens to still be recent from before
    the restart.
    """
    SQL_Connection = Command_Namespace["SQL_Connection"]
    SQL_Cursor = Command_Namespace["SQL_Cursor"]
    Pass_Label = "startup" if Initial_Startup else "scheduled"
    print("Scheduled : checking due tasks (%s), %s" % (Pass_Label, datetime.datetime.now(datetime.timezone.utc).isoformat()))
    if Initial_Startup:
        Timings = sql_task_scheduler.Timings_Get_Run_On_Startup(SQL_Cursor)
    else:
        Now = datetime.datetime.now(datetime.timezone.utc)
        Timings = [T for T in sql_task_scheduler.Timings_Get_All_Except(SQL_Cursor, "scheduler_loop") if _Is_Due(T, Now)]
    for Timing in Timings:
        print("Scheduled : running %s block '%s' (timing_id %d)" % (Pass_Label, Timing["name"], Timing["timing_id"]))
        try:
            await _Run_Scheduled_Block(Timing, Command_Namespace)
        except Exception as Error:
            # One block failing should not stop the others in this pass, and should not mark
            # this block's update_time as refreshed - a failed run is retried next pass. Since
            # a normal pass's due-check works off the fixed grid rather than update_time, this
            # stays "late for one slot" rather than shifting every future slot for this entry.
            print("Scheduled : %s block '%s' hit an error: %r" % (Pass_Label, Timing["name"], Error))
            continue
        sql_task_scheduler.Timing_Update_Time(SQL_Connection, SQL_Cursor, Timing["timing_id"])
    print("Scheduled : check complete (%s)" % Pass_Label)

def _Next_Due_At(Timing, After):
    """The next timestamp on this entry's own fixed grid at or after `After`.

    The grid is offset_seconds, offset_seconds + interval_seconds,
    offset_seconds + 2*interval_seconds, ... measured from _EPOCH - entirely independent per
    entry. Two entries sharing the same interval_seconds but different offset_seconds sit a
    constant distance apart on their own grids forever, since neither grid's boundaries depend
    on when either entry actually last ran.
    """
    Interval = Timing["interval_seconds"]
    Offset = Timing["offset_seconds"]
    Seconds_Since_Offset = (After - _EPOCH).total_seconds() - Offset
    Steps_Elapsed = math.ceil(Seconds_Since_Offset / Interval)
    return _EPOCH + datetime.timedelta(seconds=Offset + Steps_Elapsed * Interval)

def _Is_Due(Timing, Now):
    """Whether this entry's grid has produced a boundary that update_time hasn't caught yet."""
    Interval = Timing["interval_seconds"]
    if Interval <= 0:
        return False

    Update_Time = Timing["update_time"]
    if Update_Time.tzinfo is None:
        Update_Time = Update_Time.replace(tzinfo=datetime.timezone.utc)

    Due_At = _Next_Due_At(Timing, Update_Time)
    return Now >= Due_At

async def _Run_Scheduled_Block(Timing, Command_Namespace):
    """Dispatches a due timing entry to the functions it should run, by name."""
    if Timing["name"] == "wom":
        await _Wom(Command_Namespace)
    elif Timing["name"] == "discord":
        await _Discord(Command_Namespace)
    else:
        print("Scheduled : no handler wired up for timing '%s', skipping" % Timing["name"])

async def _Wom(Command_Namespace):
    """Example block: whatever simple functions should run on the "wom" timing's cadence.
    Swap these placeholder calls for the real ones once decided.
    """
    SQL_Connection = Command_Namespace["SQL_Connection"]
    SQL_Cursor = Command_Namespace["SQL_Cursor"]
    WOM_USER = Command_Namespace["WOM_USER"]
    WOM_TOKEN = Command_Namespace["WOM_TOKEN"]
    WOM_GUILD = Command_Namespace["WOM_GUILD"]

    #Get osrs guild members
    print("WOM : Getting Guild Members")
    OSRS_Guild_Member_List = await wom_data.Members_Get(WOM_USER, WOM_TOKEN, WOM_GUILD)
    #Update osrs guild members in the MySQL Database
    print("WOM : Updating Guild Members and Roles")
    sql_account_osrs.Members_List_And_Roles_List_Update(SQL_Connection, SQL_Cursor, OSRS_Guild_Member_List)
    print("Scheduled : wom block ran")

async def _Discord(Command_Namespace):
    client = Command_Namespace["DISCORD_CLIENT"]
    SQL_Connection = Command_Namespace["SQL_Connection"]
    SQL_Cursor = Command_Namespace["SQL_Cursor"]
    DISCORD_GUILD = Command_Namespace["DISCORD_GUILD"]

    #Get guild roles
    print("Discord : Getting Guild Roles")
    Guild_Role_List = await discord_data.Roles_Get(client, guild_id=DISCORD_GUILD)
    print("Discord : Updating Guild Roles")
    sql_account_discord.Roles_List_Update(SQL_Connection, SQL_Cursor, Guild_Role_List)
    #Get discord guild members
    print("Discord : Getting Guild Members")
    Discord_Guild_Member_List = discord_data.Members_Get(client, guild_id=DISCORD_GUILD)
    #Update discord guild members in the MySQL Database
    print("Discord : Updating Guild Members")
    sql_account_discord.Members_List_Update(SQL_Connection, SQL_Cursor, Discord_Guild_Member_List)