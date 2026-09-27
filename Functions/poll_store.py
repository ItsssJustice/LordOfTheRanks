# Storage for polls and the votes cast in them, backed by SQL (see sql_poll.py
# for the raw queries against polls / poll_answers / poll_votes).
#
# A "Record" here is a plain dict shaped like the old JSON record, so
# poll_view.py, poll_format.py and the poll commands barely had to change:
#   poll_id            the poll's real identity, and its ONLY identity now -
#                       there is no label any more. Poll_Key_Encode(poll_id)
#                       is the short, opaque, base64 form of it shown in the
#                       poll's footer and typed into every command's poll_id
#                       option; Poll_Key_Decode reverses that.
#   question / answers[] / multiple / closes_at / closed / created_at /
#   closed_at / applied_at / applied
#   poll_type           0 generic, 1 promotion, 2 demotion (see sql_poll)
#   channel_id / message_id
#   subject_id / subject_name          the member the poll is about, or None
#   author_id / author_name            who ran the command that opened it
#   applied_id / applied_name          who ran /pollgrant on it, if it has been
#   promotion_rank_id_current / promotion_rank_id_new, and the
#   role_id / role_name / from_role_id / from_role_name resolved fresh from
#   them each time (see _Hydrate) - a renamed role shows up immediately,
#   rather than freezing whatever it was when the poll opened, as the old JSON
#   copies did. Icons are NOT part of the hydrated Record: they need a live
#   discord.Role/Guild to look up (see rank_ladder.Icon), which a plain SQL
#   read has no access to, so callers that need one (Commands/promotions.py,
#   Commands/polls.py) look it up themselves once they hold the Role.
#   The trade-off with role_id/role_name: a closed-but-not-yet-applied poll
#   resolves /pollgrant's role to whatever discord_promotion_ranks CURRENTLY
#   maps that rank to, not necessarily the role that was live when the vote
#   was opened.
#   votes { str(discord_id) : [answer_id, ...] }

import base64
import binascii
import datetime
from Functions import sql_poll

# How far back the autocompletes look by default. Typing anything reaches past
# this, so nothing ever becomes unreachable - it only stops the list being
# every poll ever held.
RECENT_DAYS = 30


def Poll_Key_Encode(Poll_Id):
    """The poll's id, shown at the bottom of the poll and typed into every
    command as poll_id. Always exactly 8 characters: base64 of the id packed
    into a fixed 4 bytes (comfortably covers polls.poll_id's INT range), so it
    neither grows for a big id nor shrinks for a small one.

    Note the padding character for a small id is 'A', not the digit '0': '0'
    is itself a real base64 symbol (value 52 in the alphabet), so using it as
    a distinguishable left-pad character would risk corrupting the decode of
    a real id whose encoding happens to start with one. 'A' is base64's own
    symbol for six zero bits, so a leading run of them is unambiguous.
    """
    Raw = int(Poll_Id).to_bytes(4, "big")
    return base64.urlsafe_b64encode(Raw).decode("ascii")


def Poll_Key_Decode(Key):
    """The poll_id an 8-character Poll_Key_Encode string represents, or None
    if it isn't one."""
    if not Key or len(Key) != 8:
        return None
    try:
        Raw = base64.urlsafe_b64decode(Key)
    except (ValueError, binascii.Error):
        return None
    if len(Raw) != 4:
        return None
    return int.from_bytes(Raw, "big")


def As_Aware(Value):
    """A datetime read back from MySQL (naive, but UTC by convention throughout
    this bot) as a timezone-aware UTC datetime, for discord.utils.format_dt and
    for comparing against datetime.datetime.now(timezone.utc)."""
    if Value is None:
        return None
    if Value.tzinfo is None:
        return Value.replace(tzinfo=datetime.timezone.utc)
    return Value


def _Hydrate(SQL_Cursor, Row):
    """Turn a raw `polls` row into the Record dict the rest of the poll code expects."""
    if Row is None:
        return None
    Poll_Id = Row["poll_id"]

    Answers = [A["answer_text"] for A in sql_poll.Poll_Answers_Get(SQL_Cursor, Poll_Id)]

    Votes = {}
    for V in sql_poll.Poll_Votes_Get(SQL_Cursor, Poll_Id):
        Votes.setdefault(str(V["discord_id"]), []).append(V["answer_id"])
    for Key in Votes:
        Votes[Key].sort()

    New_Rank = sql_poll.Promotion_Rank_Get(SQL_Cursor, Row.get("promotion_rank_id_new"))
    Current_Rank = sql_poll.Promotion_Rank_Get(SQL_Cursor, Row.get("promotion_rank_id_current"))

    Record = dict(Row)
    Record["answers"] = Answers
    Record["votes"] = Votes
    Record["author_name"] = sql_poll.Discord_Member_Name_Get(SQL_Cursor, Row.get("author_id"))
    Record["subject_name"] = sql_poll.Discord_Member_Name_Get(SQL_Cursor, Row.get("subject_id"))
    Record["applied_name"] = sql_poll.Discord_Member_Name_Get(SQL_Cursor, Row.get("applied_id"))
    Record["role_id"] = New_Rank["discord_role_id"] if New_Rank else None
    Record["role_name"] = New_Rank["discord_role_name"] if New_Rank else None
    Record["from_role_id"] = Current_Rank["discord_role_id"] if Current_Rank else None
    Record["from_role_name"] = Current_Rank["discord_role_name"] if Current_Rank else None
    return Record


def Find_By_Id(SQL_Cursor, Poll_Id):
    return _Hydrate(SQL_Cursor, sql_poll.Poll_Get(SQL_Cursor, Poll_Id))


def Find_By_Key(SQL_Cursor, Key):
    """The poll a Poll_Key_Encode string refers to, or None if it doesn't
    decode to a real poll. This is what every command uses to resolve its
    poll_id option."""
    Poll_Id = Poll_Key_Decode(Key)
    if Poll_Id is None:
        return None
    return Find_By_Id(SQL_Cursor, Poll_Id)


def Open_Records(SQL_Cursor):
    """Every poll still open, hydrated. Used to re-register buttons at start-up."""
    return [_Hydrate(SQL_Cursor, Row) for Row in sql_poll.Polls_Search(SQL_Cursor, Only_Open=True)]


def Expired_Unclosed_Records(SQL_Cursor):
    """Polls past their deadline but not closed yet, hydrated. Used by the expired-poll closer loop."""
    return [_Hydrate(SQL_Cursor, Row) for Row in sql_poll.Polls_Expired_Unclosed_Get(SQL_Cursor)]


def Is_Rank_Vote(Record):
    return Record.get("poll_type") in (sql_poll.POLL_TYPE_PROMOTION, sql_poll.POLL_TYPE_DEMOTION)


def _Choice_Pairs(Rows, Current):
    """(poll_id_key, display_text) pairs for autocomplete. Only the poll id is
    shown, and Current - whatever the user has typed so far - filters by the
    start of the id, ignoring case.
    """
    Current = (Current or "").strip().lower()
    Out = []
    for R in Rows:
        Key = Poll_Key_Encode(R["poll_id"])
        if Current and not Key.lower().startswith(Current):
            continue
        Out.append((Key, Key))
    return Out


def Grantable_Choices(SQL_Cursor, Current=""):
    """Votes still waiting to be applied by hand, newest first: closed rank
    votes about somebody that passed and haven't been applied. Votes that
    didn't pass are left out, as are ones the bot applied automatically when
    they closed. Without typed text this is limited to the last RECENT_DAYS;
    typing anything searches the lot, so an older vote is still reachable.
    """
    Since = None if (Current or "").strip() else (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=RECENT_DAYS))
    Rows = sql_poll.Polls_Search(SQL_Cursor, Only_Open=False, Only_Rank_Votes=True,
                                  Require_Subject=True, Exclude_Applied=True, Since=Since, Only_Passed=True)
    return _Choice_Pairs(Rows, Current)


def Recent_Choices(SQL_Cursor, Current=""):
    """Every poll, newest first, trimmed to the recent window when not searching."""
    Since = None if (Current or "").strip() else (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=RECENT_DAYS))
    Rows = sql_poll.Polls_Search(SQL_Cursor, Since=Since)
    return _Choice_Pairs(Rows, Current)


def Open_Choices(SQL_Cursor, Current=""):
    Rows = sql_poll.Polls_Search(SQL_Cursor, Only_Open=True)
    return _Choice_Pairs(Rows, Current)


def Create(SQL_Connection, SQL_Cursor, Channel_Id, Author_Id, Question, Answers, Multiple, Hours,
           Poll_Type=None, Subject_Id=None, Promotion_Rank_Id_Current=None, Promotion_Rank_Id_New=None):
    Poll_Type = sql_poll.POLL_TYPE_GENERIC if Poll_Type is None else Poll_Type
    Closes_At = datetime.datetime.utcnow() + datetime.timedelta(hours=Hours)
    Poll_Id = sql_poll.Poll_Insert(
        SQL_Connection, SQL_Cursor, Channel_Id, Author_Id, Poll_Type, Question, Answers,
        Multiple, Closes_At, Subject_Id, Promotion_Rank_Id_Current, Promotion_Rank_Id_New)
    return Find_By_Id(SQL_Cursor, Poll_Id)


def Attach_Message(SQL_Connection, SQL_Cursor, Poll_Id, Message_Id):
    sql_poll.Poll_Message_Attach(SQL_Connection, SQL_Cursor, Poll_Id, Message_Id)


def Is_Closed(Record):
    """Closed either because it was closed by hand, or because its time ran out."""
    if Record.get("closed"):
        return True
    return datetime.datetime.now(datetime.timezone.utc) >= As_Aware(Record["closes_at"])


def Close(SQL_Connection, SQL_Cursor, Poll_Id):
    sql_poll.Poll_Close(SQL_Connection, SQL_Cursor, Poll_Id)
    return Find_By_Id(SQL_Cursor, Poll_Id)


def Mark_Applied(SQL_Connection, SQL_Cursor, Poll_Id, Applied_By_Discord_Id):
    """Record that a vote has been acted on, so it drops out of the grant list."""
    sql_poll.Poll_Mark_Applied(SQL_Connection, SQL_Cursor, Poll_Id, Applied_By_Discord_Id)
    return Find_By_Id(SQL_Cursor, Poll_Id)


def Record_Vote(SQL_Connection, SQL_Cursor, Poll_Id, User_Id, Answer_Index):
    """Store one vote, addressed by poll_id (the buttons carry Poll_Key_Encode(poll_id)).

    Returns (accepted, message_for_the_voter).
    """
    Record = Find_By_Id(SQL_Cursor, Poll_Id)
    if Record is None:
        return False, "That poll no longer exists."
    if Is_Closed(Record):
        return False, "Voting on this poll has closed."
    # Nobody votes on their own promotion or demotion
    if Is_Rank_Vote(Record) and Record.get("subject_id") == User_Id:
        return False, "You can't vote on a promotion or demotion vote about yourself."

    Current = sql_poll.Poll_Vote_Get_For(SQL_Cursor, Poll_Id, User_Id)

    if Record["multiple"]:
        if Answer_Index in Current:
            New_Answers = [i for i in Current if i != Answer_Index]
            Note = "Removed your vote for **%s**." % Record["answers"][Answer_Index]
        else:
            New_Answers = sorted(Current + [Answer_Index])
            Note = "Added your vote for **%s**." % Record["answers"][Answer_Index]
    else:
        Previous = Current[0] if Current else None
        New_Answers = [Answer_Index]
        if Previous == Answer_Index:
            Note = "You already voted for **%s**. No change." % Record["answers"][Answer_Index]
        elif Previous is None:
            Note = "Vote recorded for **%s**." % Record["answers"][Answer_Index]
        else:
            Note = "Vote changed from **%s** to **%s**." % (Record["answers"][Previous],
                                                            Record["answers"][Answer_Index])

    sql_poll.Poll_Vote_Replace(SQL_Connection, SQL_Cursor, Poll_Id, User_Id, New_Answers)
    return True, Note


def Tally(Record):
    """[(answer_text, count)] plus the number of distinct people who voted."""
    Counts = [0] * len(Record["answers"])
    for Picks in Record["votes"].values():
        for i in Picks:
            if 0 <= i < len(Counts):
                Counts[i] += 1
    return list(zip(Record["answers"], Counts)), len(Record["votes"])


def Voters_By_Answer(Record):
    """[(answer_text, [user_id, ...])]"""
    Out = [(Text, []) for Text in Record["answers"]]
    for User_Id, Picks in Record["votes"].items():
        for i in Picks:
            if 0 <= i < len(Out):
                Out[i][1].append(int(User_Id))
    return Out
