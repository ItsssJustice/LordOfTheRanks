# Helpers for turning a Poll into something readable.
#
# WHY THIS EXISTS:
# discord.py exposes Poll.victor_answer, but it is only ever filled in from the
# separate "poll result" system message Discord posts into the channel when a
# poll ends (MessageType.poll_result). A Poll you got back from
# channel.fetch_message() has victor_answer == None even when the poll has very
# clearly finished and has a runaway winner. So we work the winner out from the
# vote counts ourselves, and treat victor_answer as a bonus if it happens to be there.

def Winners(Poll):
    """Return the list of answers tied for first place. Empty if nobody voted."""
    # Trust discord's own answer if it managed to populate it
    if getattr(Poll, "victor_answer", None) is not None:
        return [Poll.victor_answer]

    Top = max((Answer.vote_count for Answer in Poll.answers), default=0)
    if Top == 0:
        return []
    return [Answer for Answer in Poll.answers if Answer.vote_count == Top]

def Outcome(Poll):
    """One-line human summary of how a finished poll landed."""
    Won = Winners(Poll)
    if not Won:
        return "Closed with no votes cast."
    if len(Won) == 1:
        return "Winner: **%s** (%d vote(s))" % (Won[0].text, Won[0].vote_count)
    return "Tied on %d vote(s): %s" % (Won[0].vote_count, ", ".join("**%s**" % A.text for A in Won))

def Bar(Vote_Count, Total, Width=20):
    """Crude text bar so results are skimmable in chat."""
    Share = (Vote_Count / Total * 100) if Total else 0
    return "#" * int(Share / (100 / Width)), Share
