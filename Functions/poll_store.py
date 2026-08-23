# Keeps a record of every poll this bot has created.
#
# Discord does NOT let you search for "my polls" later, and a Poll object only
# exists as part of the Message that carries it. So to read results back after a
# restart the only thing you actually need to remember is the channel id + message
# id. This module is that memory, written to a small JSON file next to the bot.

import os
import json

Store_Path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "Polls.json")

def Get():
    """Return the whole {label: record} mapping, or {} if nothing is stored yet."""
    if not os.path.isfile(Store_Path):
        return {}
    with open(Store_Path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print("Polls.json is corrupt, starting from an empty store")
            return {}

def Find(Label):
    """Return a single poll record by its label, or None."""
    return Get().get(Label.lower())

def Save(Label, Guild_Id, Channel_Id, Message_Id, Question, Answers=None):
    """Record a freshly created poll so it can be looked up later by label.

    Answers are stored purely so /pollgrant can autocomplete them without
    having to hit the API on every keystroke.
    """
    Polls = Get()
    Polls[Label.lower()] = {
        "label": Label,
        "guild_id": Guild_Id,
        "channel_id": Channel_Id,
        "message_id": Message_Id,
        "question": Question,
        "answers": Answers or []
    }
    with open(Store_Path, "w", encoding="utf-8") as f:
        json.dump(Polls, f, indent=4)
    return Polls[Label.lower()]

def Labels():
    """All known labels, for the slash-command autocomplete."""
    return [Record["label"] for Record in Get().values()]

def Display(Polls):
    """Console dump, in the same spirit as guild_roles.Display."""
    print("Polls on record: % d" % len(Polls))
    for Record in Polls.values():
        print("  [% s] '% s' -> channel % s / message % s"
              % (Record["label"], Record["question"], Record["channel_id"], Record["message_id"]))
