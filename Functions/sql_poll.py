# Raw SQL for polls, promotion votes and demotion votes.
#
# This module owns every query against polls / poll_answers / poll_votes /
# poll_type, plus the small discord_promotion_ranks / discord_roles /
# discord_members lookups the poll system needs (resolving a rank to a role's
# name and icon, resolving a discord_id to a display name). poll_store.py is
# the layer above this: it turns these rows into the "Record" dict shape the
# rest of the poll code (poll_view, poll_format, the poll commands) expects.

from Functions import sql_config
import datetime

# poll_type.poll_type_id values, per MySQL_Table_Default_Data.json
POLL_TYPE_GENERIC = 0
POLL_TYPE_PROMOTION = 1
POLL_TYPE_DEMOTION = 2

# ---------------------------------------------------------------------------
# polls / poll_answers / poll_votes
# ---------------------------------------------------------------------------

_POLL_COLUMNS = (
    "poll_id, channel_id, message_id, author_id, poll_type, question, "
    "multiple, subject_id, promotion_rank_id_current, promotion_rank_id_new, "
    "created_at, closes_at, closed, closed_at, applied_at, applied_id, applied"
)

# Insert a poll and its answers as one unit. Returns the new poll_id.
def Poll_Insert(SQL_Connection, SQL_Cursor, Channel_Id, Author_Id, Poll_Type, Question,
                 Answers, Multiple, Closes_At, Subject_Id=None, Promotion_Rank_Id_Current=None,
                 Promotion_Rank_Id_New=None):
    cursor = SQL_Connection.cursor()
    try:
        Sql = """INSERT INTO polls
                 (channel_id, author_id, poll_type, question, multiple, subject_id,
                  promotion_rank_id_current, promotion_rank_id_new, closes_at)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(Sql, (Channel_Id, Author_Id, Poll_Type, Question, Multiple,
                              Subject_Id, Promotion_Rank_Id_Current, Promotion_Rank_Id_New, Closes_At))
        Poll_Id = cursor.lastrowid
        Answer_Rows = [(Poll_Id, Index, Text) for Index, Text in enumerate(Answers)]
        cursor.executemany(
            "INSERT INTO poll_answers (poll_id, answer_id, answer_text) VALUES (%s, %s, %s)",
            Answer_Rows)
        SQL_Connection.commit()
    except Exception:
        SQL_Connection.rollback()
        raise
    finally:
        cursor.close()
    return Poll_Id

# One poll row by id, or None if it doesn't exist.
def Poll_Get(SQL_Cursor, Poll_Id):
    Query = "SELECT %s FROM polls WHERE poll_id = %%s" % _POLL_COLUMNS
    Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Poll_Id,))
    return Rows[0] if Rows else None

# Every answer for a poll, in the order they were created (answer_id 0..n-1).
def Poll_Answers_Get(SQL_Cursor, Poll_Id):
    Query = "SELECT answer_id, answer_text FROM poll_answers WHERE poll_id = %s ORDER BY answer_id"
    return sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Poll_Id,)) or []

def Poll_Message_Attach(SQL_Connection, SQL_Cursor, Poll_Id, Message_Id):
    SQL_Cursor.execute("UPDATE polls SET message_id = %s WHERE poll_id = %s", (Message_Id, Poll_Id))
    SQL_Connection.commit()

def Poll_Close(SQL_Connection, SQL_Cursor, Poll_Id):
    SQL_Cursor.execute(
        "UPDATE polls SET closed = TRUE, closed_at = NOW() WHERE poll_id = %s AND closed = FALSE",
        (Poll_Id,))
    SQL_Connection.commit()

def Poll_Mark_Applied(SQL_Connection, SQL_Cursor, Poll_Id, Applied_Id):
    SQL_Cursor.execute(
        "UPDATE polls SET applied = TRUE, applied_at = NOW(), applied_id = %s WHERE poll_id = %s",
        (Applied_Id, Poll_Id))
    SQL_Connection.commit()

# Every vote row for a poll: [{"discord_id":..., "answer_id":...}, ...]
def Poll_Votes_Get(SQL_Cursor, Poll_Id):
    Query = "SELECT discord_id, answer_id FROM poll_votes WHERE poll_id = %s"
    return sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Poll_Id,)) or []

# One voter's current answer_ids for this poll, e.g. [] / [0] / [0, 2].
def Poll_Vote_Get_For(SQL_Cursor, Poll_Id, Discord_Id):
    Query = "SELECT answer_id FROM poll_votes WHERE poll_id = %s AND discord_id = %s ORDER BY answer_id"
    Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Poll_Id, Discord_Id)) or []
    return [Row["answer_id"] for Row in Rows]

# Set a voter's recorded answers for this poll to exactly Answer_Ids (delete then
# re-insert, so this is correct whether growing, shrinking or clearing the set).
def Poll_Vote_Replace(SQL_Connection, SQL_Cursor, Poll_Id, Discord_Id, Answer_Ids):
    cursor = SQL_Connection.cursor()
    try:
        cursor.execute("DELETE FROM poll_votes WHERE poll_id = %s AND discord_id = %s",
                        (Poll_Id, Discord_Id))
        if Answer_Ids:
            Rows = [(Poll_Id, Discord_Id, Answer_Id) for Answer_Id in Answer_Ids]
            cursor.executemany(
                "INSERT INTO poll_votes (poll_id, discord_id, answer_id) VALUES (%s, %s, %s)", Rows)
        SQL_Connection.commit()
    except Exception:
        SQL_Connection.rollback()
        raise
    finally:
        cursor.close()

# Polls matching the given filters, newest (created_at) first. Backs every
# autocomplete list poll_store exposes (Grantable_Choices / Recent_Choices /
# Open_Choices) from one flexible query rather than three. There is no text
# search here any more (there's no label to search, and poll_store filters the
# result by the typed text - against the question, or a poll id prefix -
# itself, since a poll id isn't something SQL can LIKE-match against).
#   Only_Open        True: still open  /  False: closed  /  None: either
#   Only_Rank_Votes   limit to poll_type IN (PROMOTION, DEMOTION)
#   Require_Subject   subject_id IS NOT NULL
#   Exclude_Applied   applied = FALSE
#   Only_Passed       the first answer ("Yes" on a rank vote) has strictly more
#                     votes than the second - the same test granting uses
#   Since             only polls created_at >= this datetime
def Polls_Search(SQL_Cursor, Only_Open=None, Only_Rank_Votes=False,
                  Require_Subject=False, Exclude_Applied=False, Since=None, Only_Passed=False):
    Where = []
    Params = []
    if Only_Open is not None:
        # Bound as a parameter computed here in Python, not MySQL's own NOW():
        # everywhere else in the bot (poll_store.Is_Closed) treats the stored,
        # naive closes_at as UTC and compares it against Python's own UTC
        # clock. Trusting NOW() instead would silently disagree the moment
        # the database server's session timezone isn't UTC too.
        Now = datetime.datetime.utcnow()
        if Only_Open is True:
            Where.append("closed = FALSE AND closes_at > %s")
        else:
            Where.append("(closed = TRUE OR closes_at <= %s)")
        Params.append(Now)
    if Only_Rank_Votes:
        Where.append("poll_type IN (%d, %d)" % (POLL_TYPE_PROMOTION, POLL_TYPE_DEMOTION))
    if Require_Subject:
        Where.append("subject_id IS NOT NULL")
    if Exclude_Applied:
        Where.append("applied = FALSE")
    if Only_Passed:
        Where.append("(SELECT COUNT(*) FROM poll_votes AS v WHERE v.poll_id = polls.poll_id AND v.answer_id = 0)"
                     " > (SELECT COUNT(*) FROM poll_votes AS v WHERE v.poll_id = polls.poll_id AND v.answer_id = 1)")
    if Since is not None:
        Where.append("created_at >= %s")
        Params.append(Since)
    Where_Sql = ("WHERE " + " AND ".join(Where)) if Where else ""
    Query = "SELECT %s FROM polls %s ORDER BY created_at DESC" % (_POLL_COLUMNS, Where_Sql)
    return sql_config.Query_Dicts_Get(SQL_Cursor, Query, tuple(Params)) or []

# Polls whose deadline has passed but that haven't been closed yet - what the
# expired-poll closer loop (poll_setup.Close_Expired_Polls) needs each minute,
# rather than every poll ever held. Deadline compared against Python's UTC clock,
# for the same reason as Polls_Search.
def Polls_Expired_Unclosed_Get(SQL_Cursor):
    Query = "SELECT %s FROM polls WHERE closed = FALSE AND closes_at <= %%s ORDER BY closes_at" % _POLL_COLUMNS
    return sql_config.Query_Dicts_Get(SQL_Cursor, Query, (datetime.datetime.utcnow(),)) or []

# The newest promotion or demotion vote about this member that is still open, or
# None. Open means not closed by hand and not past its deadline, reckoned against
# Python's UTC clock the same way as poll_store.Is_Closed.
def Rank_Vote_Open_For_Subject_Get(SQL_Cursor, Subject_Id):
    Query = ("SELECT %s FROM polls WHERE subject_id = %%s AND poll_type IN (%d, %d) "
             "AND closed = FALSE AND closes_at > %%s ORDER BY created_at DESC LIMIT 1"
             % (_POLL_COLUMNS, POLL_TYPE_PROMOTION, POLL_TYPE_DEMOTION))
    Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Subject_Id, datetime.datetime.utcnow()))
    return Rows[0] if Rows else None

# ---------------------------------------------------------------------------
# Rank ladder support (discord_promotion_ranks / discord_roles)
# ---------------------------------------------------------------------------

# Every rank a vote can involve, highest promotion_rank_id first, excluding
# promotion_rank_id 0 ("not in clan" - not a rank to vote onto or off of).
#
# The ORDER here only decides which rank wins when a member holds several.
# Which rank a promotion or demotion leads to comes from
# promotion_rank_id_progression, each rank's pointer to its next rank - see
# rank_ladder.py.
def Promotion_Rank_Ladder_Get(SQL_Cursor):
    Query = """
        SELECT dpr.promotion_rank_id, dpr.discord_role_id, dr.discord_role_name,
               dpr.promotion_rank_id_progression
        FROM discord_promotion_ranks AS dpr
        JOIN discord_roles AS dr ON dr.discord_role_id = dpr.discord_role_id
        WHERE dpr.promotion_rank_id > 0
        ORDER BY dpr.promotion_rank_id DESC
    """
    return sql_config.Query_Dicts_Get(SQL_Cursor, Query) or []

# One rank's role id/name, or None. promotion_rank_id 0 or None both miss.
# (No icon here - icons are looked up live against the guild, see rank_ladder.Icon.)
def Promotion_Rank_Get(SQL_Cursor, Promotion_Rank_Id):
    if not Promotion_Rank_Id:
        return None
    Query = """
        SELECT dpr.promotion_rank_id, dpr.discord_role_id, dr.discord_role_name
        FROM discord_promotion_ranks AS dpr
        JOIN discord_roles AS dr ON dr.discord_role_id = dpr.discord_role_id
        WHERE dpr.promotion_rank_id = %s
    """
    Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Promotion_Rank_Id,))
    return Rows[0] if Rows else None

# The promotion_rank_id a discord_role_id maps to, or None if it isn't on the ladder.
def Promotion_Rank_For_Role(SQL_Cursor, Discord_Role_Id):
    if not Discord_Role_Id:
        return None
    Query = ("SELECT promotion_rank_id FROM discord_promotion_ranks "
             "WHERE discord_role_id = %s AND promotion_rank_id > 0")
    Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Discord_Role_Id,))
    return Rows[0]["promotion_rank_id"] if Rows else None

# ---------------------------------------------------------------------------
# discord_members name lookups (for author_id / subject_id / applied_id)
# ---------------------------------------------------------------------------

def Discord_Member_Name_Get(SQL_Cursor, Discord_Id):
    """Best-effort display name for a discord_id, or None if it isn't known."""
    if not Discord_Id:
        return None
    Query = ("SELECT name_display, name_nick, name_global, name_user "
             "FROM discord_members WHERE discord_id = %s")
    Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Discord_Id,))
    if not Rows:
        return None
    Row = Rows[0]
    return Row.get("name_display") or Row.get("name_nick") or Row.get("name_global") or Row.get("name_user")
