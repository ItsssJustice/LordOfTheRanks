# Turning a tally into something readable.

# The two characters a result bar is drawn from. Parallelograms rather than solid
# blocks: lighter on the eye at a glance, and they leave the row looking like a
# gauge rather than a wall. Swap this pair to restyle every bar at once.
FILLED = "▰"   # black parallelogram
EMPTY  = "▱"   # white parallelogram

def Rank_Result(Tally):
    """Pass or fail for a Yes/No rank vote.

    Deliberately does not name the answers. The question gives both ranks, each
    bar gives them again, and with only two options a tie can only ever be
    between those two - so repeating them a third time says nothing.
    """
    Won = Winners(Tally)
    if not Won:
        return "no votes cast"
    if len(Won) > 1:
        return "tied on %d vote(s), no change" % max(Count for _, Count in Tally)
    return "passed" if Won[0] == Tally[0][0] else "did not pass"

def Short_Result(Tally):
    """How a finished vote landed, compact enough for a line on the posted message.

    Outcome() is the fuller sentence used in command replies; this is the same
    fact said in as few words as will fit under the bars.
    """
    Won = Winners(Tally)
    if not Won:
        return "no votes cast"
    Top = max(Count for _, Count in Tally)
    if len(Won) == 1:
        return "**%s** with %d vote(s)" % (Won[0], Top)
    return "tied on %d vote(s) - %s" % (Top, ", ".join("**%s**" % W for W in Won))

def Bar(Vote_Count, Total, Width=12):
    """A filled/unfilled block bar, and the share it represents.

    Block characters rather than hashes, and a fixed width so every row is the
    same length whatever the counts are.
    """
    Share = (Vote_Count / Total * 100) if Total else 0
    Filled = int(round(Share / 100 * Width))
    return FILLED * Filled + EMPTY * (Width - Filled), Share

def Result_Line(Text, Vote_Count, Total):
    """One answer's row on a finished poll.

    The bar and the percentage sit inside a code span so they are monospaced:
    that is what keeps every row lining up, since the answer text beside them is
    proportional and often carries an emoji of its own width.
    """
    Drawn, Share = Bar(Vote_Count, Total)
    return "`%s %3.0f%%`  %s  (%d)" % (Drawn, Share, Text, Vote_Count)

def Winners(Tally):
    """Answers tied for first place. Empty if nobody voted."""
    Top = max((Count for _, Count in Tally), default=0)
    if Top == 0:
        return []
    return [Text for Text, Count in Tally if Count == Top]

def Outcome(Tally):
    """One-line summary of how a finished poll landed."""
    Won = Winners(Tally)
    if not Won:
        return "Closed with no votes cast."
    Top = max(Count for _, Count in Tally)
    if len(Won) == 1:
        return "Winner: **%s** (%d vote(s))" % (Won[0], Top)
    return "Tied on %d vote(s): %s" % (Top, ", ".join("**%s**" % W for W in Won))
