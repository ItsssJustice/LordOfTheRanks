# Storage for secret-ballot polls.
#
# Unlike a native discord Poll, nothing about these votes lives on discord's
# side -- the message only ever shows a question and some buttons. Who voted for
# what exists solely in this file, which is why the ballot can actually be secret.
#
# One JSON file, one record per poll:
#   label, guild_id, channel_id, message_id, question, answers[],
#   multiple, live_counts, closes_at (iso8601), closed (bool),
#   votes { user_id : [answer indexes] }

import os
import json
import datetime

Store_Path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "SecretPolls.json")

def Get():
    if not os.path.isfile(Store_Path):
        return {}
    with open(Store_Path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print("SecretPolls.json is corrupt, starting from an empty store")
            return {}

def _Write(Polls):
    with open(Store_Path, "w", encoding="utf-8") as f:
        json.dump(Polls, f, indent=4)

def Find(Label):
    return Get().get((Label or "").lower())

def Labels():
    return [R["label"] for R in Get().values()]

def Open_Labels():
    return [R["label"] for R in Get().values() if not Is_Closed(R)]

def Create(Label, Guild_Id, Channel_Id, Question, Answers, Multiple, Live_Counts, Hours):
    Polls = Get()
    Polls[Label.lower()] = {
        "label": Label,
        "guild_id": Guild_Id,
        "channel_id": Channel_Id,
        "message_id": None,             # filled in once the message exists
        "question": Question,
        "answers": Answers,
        "multiple": Multiple,
        "live_counts": Live_Counts,
        "closes_at": (datetime.datetime.now(datetime.timezone.utc)
                      + datetime.timedelta(hours=Hours)).isoformat(),
        "closed": False,
        "votes": {}
    }
    _Write(Polls)
    return Polls[Label.lower()]

def Attach_Message(Label, Message_Id):
    Polls = Get()
    Polls[Label.lower()]["message_id"] = Message_Id
    _Write(Polls)

def Is_Closed(Record):
    """Closed either because someone closed it, or because its time ran out."""
    if Record.get("closed"):
        return True
    Closes = datetime.datetime.fromisoformat(Record["closes_at"])
    return datetime.datetime.now(datetime.timezone.utc) >= Closes

def Close(Label):
    Polls = Get()
    R = Polls.get(Label.lower())
    if R is None:
        return None
    R["closed"] = True
    _Write(Polls)
    return R

def Record_Vote(Label, User_Id, Answer_Index):
    """Store one vote. Returns (accepted, message_for_the_voter)."""
    Polls = Get()
    R = Polls.get(Label.lower())
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
    """[(answer_text, [user_id, ...])] -- only ever used by the gated command."""
    Out = [(Text, []) for Text in Record["answers"]]
    for User_Id, Picks in Record["votes"].items():
        for i in Picks:
            if 0 <= i < len(Out):
                Out[i][1].append(int(User_Id))
    return Out
