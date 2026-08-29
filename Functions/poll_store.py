# Storage for polls and the votes cast in them.
#
# Votes are recorded here rather than by discord. The posted message only ever
# carries the question and the answer buttons, so a vote reaches this bot as an
# interaction and is written to a JSON file next to the code.
#
# One file, one record per poll:
#   label, guild_id, channel_id, message_id, question, answers[],
#   multiple, closes_at (iso8601), closed (bool),
#   key         short id used in the buttons' custom_id, see New_Key
#   kind        "generic", "promotion" or "demotion"
#   subject_id / subject_name   the member the poll is about, or None
#   role_id / role_name         the rank being voted towards, or None
#   from_role_id / from_role_name  their rank when the vote opened, or None
#
# Names are stored alongside ids so the posted message can be rendered without a
# guild lookup, and so the record still reads sensibly if a role is later deleted.
#   created_at / closed_at  when it opened, and when it actually closed
#   applied_at / applied_by when /pollgrant acted on it, if it has
#   votes { user_id : [answer indexes] }

import os
import json
import secrets
import datetime

# The longest a label may be. Labels are shown in slash-command autocomplete,
# where discord caps a choice name at 100 characters, so that is the real limit.
# Note a custom server emoji arrives as "<:name:1234567890123456789>", roughly
# thirty characters, so an emoji in a label eats a lot of this budget.
LABEL_LIMIT = 100

# How far back the autocompletes look by default. Typing a search term reaches
# past this, so nothing ever becomes unreachable - it only stops the list being
# every poll ever held.
RECENT_DAYS = 30

Store_Path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "Polls.json")

def Get():
    if not os.path.isfile(Store_Path):
        return {}
    with open(Store_Path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print("Polls.json is corrupt, starting from an empty store")
            return {}

def _Write(Polls):
    with open(Store_Path, "w", encoding="utf-8") as f:
        json.dump(Polls, f, indent=4)

def Find(Label):
    return Get().get((Label or "").lower())

def New_Key(Polls):
    """A short id for the buttons to carry.

    The label used to be embedded in each button's custom_id, which discord caps
    at 100 characters -- so a long label, or one holding a custom emoji, could
    not be used at all. The buttons now carry this instead, leaving the label
    free to be whatever reads well.
    """
    Existing = {R.get("key") for R in Polls.values()}
    while True:
        Key = secrets.token_hex(3)
        if Key not in Existing:
            return Key

def Find_By_Key(Key):
    """The poll whose buttons carry this key."""
    for Record in Get().values():
        if Record.get("key") == Key:
            return Record
    return None

def Migrate():
    """Give a key to any record made before keys existed.

    Their buttons were built from the lowercased label, so that is the key they
    have to keep or the buttons on those messages stop working.
    """
    Polls = Get()
    Changed = False
    for Store_Key, Record in Polls.items():
        if not Record.get("key"):
            Record["key"] = Store_Key
            Changed = True
    if Changed:
        _Write(Polls)
    return Changed

def Labels():
    return [R["label"] for R in _Newest_First(Get().values())]

def Mark_Applied(Label, By_Name):
    """Record that a vote has been acted on, so it drops out of the grant list."""
    Polls = Get()
    R = Polls.get(Label.lower())
    if R is None:
        return None
    R["applied_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    R["applied_by"] = By_Name
    _Write(Polls)
    return R

def Ended_At(Record):
    """When voting actually stopped: the moment it was closed, or its deadline."""
    return datetime.datetime.fromisoformat(Record.get("closed_at") or Record["closes_at"])

def Started_At(Record):
    """Records made before created_at existed fall back to their deadline."""
    return datetime.datetime.fromisoformat(Record.get("created_at") or Record["closes_at"])

def _Newest_First(Records):
    return sorted(Records, key=Started_At, reverse=True)

def Grantable_Labels(Search=""):
    """Votes /pollgrant could actually act on, newest first.

    Closed, about somebody, and not already applied. Without a search term this
    is limited to the last RECENT_DAYS, because otherwise the list grows without
    end and the useful entry is buried. Typing anything searches the lot, so an
    older vote is still reachable.
    """
    Search = (Search or "").lower()
    Cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=RECENT_DAYS))
    Out = []
    for R in _Newest_First(Get().values()):
        # Same test /pollgrant applies: a generic poll has no affirmative answer
        # for it to read, even if an old record happens to name a subject.
        if not R.get("subject_id") or R.get("applied_at") or not Is_Rank_Vote(R):
            continue
        if not Is_Closed(R):
            continue
        if Search:
            if Search not in R["label"].lower() and Search not in R["question"].lower():
                continue
        elif Ended_At(R) < Cutoff:
            continue
        Out.append(R["label"])
    return Out

def Recent_Labels(Search=""):
    """Every poll, newest first, trimmed to the recent window when not searching."""
    Search = (Search or "").lower()
    Cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=RECENT_DAYS))
    Out = []
    for R in _Newest_First(Get().values()):
        if Search:
            if Search not in R["label"].lower() and Search not in R["question"].lower():
                continue
        elif Started_At(R) < Cutoff:
            continue
        Out.append(R["label"])
    return Out

def Open_Labels():
    return [R["label"] for R in _Newest_First(Get().values()) if not Is_Closed(R)]

def Create(Label, Guild_Id, Channel_Id, Question, Answers, Multiple, Hours, Extra=None):
    Polls = Get()
    Polls[Label.lower()] = {
        "label": Label,
        "key": New_Key(Polls),
        "guild_id": Guild_Id,
        "channel_id": Channel_Id,
        "message_id": None,             # filled in once the message exists
        "question": Question,
        "answers": Answers,
        "multiple": Multiple,
        "kind": "generic",
        "subject_id": None,
        "subject_name": None,
        "role_id": None,
        "role_name": None,
        "from_role_id": None,
        "from_role_name": None,
        "closes_at": (datetime.datetime.now(datetime.timezone.utc)
                      + datetime.timedelta(hours=Hours)).isoformat(),
        "closed": False,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "closed_at": None,
        "applied_at": None,
        "applied_by": None,
        "votes": {}
    }
    if Extra:
        Polls[Label.lower()].update(Extra)
    _Write(Polls)
    return Polls[Label.lower()]

def Is_Rank_Vote(Record):
    return Record.get("kind") in ("promotion", "demotion")

def Attach_Message(Label, Message_Id):
    Polls = Get()
    Polls[Label.lower()]["message_id"] = Message_Id
    _Write(Polls)

def Is_Closed(Record):
    """Closed either because it was closed by hand, or because its time ran out."""
    if Record.get("closed"):
        return True
    return datetime.datetime.now(datetime.timezone.utc) >= datetime.datetime.fromisoformat(Record["closes_at"])

def Close(Label):
    Polls = Get()
    R = Polls.get(Label.lower())
    if R is None:
        return None
    R["closed"] = True
    R["closed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _Write(Polls)
    return R

def Record_Vote(Key, User_Id, Answer_Index):
    """Store one vote, addressed by the key the buttons carry.

    Returns (accepted, message_for_the_voter).
    """
    Polls = Get()
    R = next((Rec for Rec in Polls.values() if Rec.get("key") == Key), None)
    if R is None:
        return False, "That poll no longer exists."
    if Is_Closed(R):
        return False, "Voting on this poll has closed."

    Key = str(User_Id)
    Current = R["votes"].get(Key, [])

    if R["multiple"]:
        if Answer_Index in Current:
            Current.remove(Answer_Index)
            Note = "Removed your vote for **%s**." % R["answers"][Answer_Index]
        else:
            Current.append(Answer_Index)
            Note = "Added your vote for **%s**." % R["answers"][Answer_Index]
        if Current:
            R["votes"][Key] = sorted(Current)
        else:
            R["votes"].pop(Key, None)
    else:
        Previous = Current[0] if Current else None
        R["votes"][Key] = [Answer_Index]
        if Previous == Answer_Index:
            Note = "You already voted for **%s**. No change." % R["answers"][Answer_Index]
        elif Previous is None:
            Note = "Vote recorded for **%s**." % R["answers"][Answer_Index]
        else:
            Note = "Vote changed from **%s** to **%s**." % (R["answers"][Previous],
                                                            R["answers"][Answer_Index])
    _Write(Polls)
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
