# Who may open a promotion or demotion vote, and onto which rank.
#
# On top of the moderator level 1 check every rank vote command makes:
#
#   Both directions
#     Nobody may open a vote on themselves.
#     Only one rank vote runs on a member at a time: while a promotion or demotion
#     vote about them is still open, no other can be opened on them.
#
#   Promotions
#     1. The caller's own rank must be equal to or above the rank the member would
#        hold if the vote passed. Rank order is promotion_rank_id, the same order
#        as the vote ladder (see sql_poll.Promotion_Rank_Ladder_Get).
#     2. Promoting to the caller's OWN rank additionally needs them to have held
#        that rank for moderator_promotion_equal_rank_delay_days (bot_config).
#        When they got it is discord_members.promotion_rank_updated_at, stamped by
#        sql_account_discord.Members_List_Update whenever the synced rank changes.
#        NULL there means the rank predates tracking, so no wait is owed.
#
#   Demotions
#     The member being demoted must currently hold a rank strictly below the
#     caller's own.
#
# Rank_Vote_Start_Permitted returns (code, details) for the command layer to phrase:
#   None                  allowed
#   "self_vote"           the caller is the member being voted on
#   "vote_in_progress"    a promotion/demotion vote on this member is still open - details["poll"]
#   "caller_no_rank"      the caller holds no rank on the ladder
#   "rank_too_low"        promotion rule 1 - details["caller_role"]
#   "equal_rank_wait"     promotion rule 2, still inside the wait - details["until"], details["wait_days"]
#   "rank_sync_pending"   the caller's live rank differs from the synced one, so they
#                         changed rank since the last discord sync - treated as a
#                         fresh promotion until the sync catches up
#   "config_missing"      moderator_promotion_equal_rank_delay_days isn't in bot_config
#   "subject_not_below"   demotion of a member at or above the caller's rank - details["caller_role"]

import datetime
from Functions import bot_config, sql_poll, sql_promotion, rank_ladder

EQUAL_RANK_DELAY_CONFIG = "moderator_promotion_equal_rank_delay_days"

def Rank_Vote_Start_Permitted(SQL_Cursor, Caller, Subject, Subject_Role, Target_Role, Direction):
	Details = {}
	if Caller.id == Subject.id:
		return "self_vote", Details
	Open_Vote = sql_poll.Rank_Vote_Open_For_Subject_Get(SQL_Cursor, Subject.id)
	if Open_Vote is not None:
		Details["poll"] = Open_Vote
		return "vote_in_progress", Details
	Caller_Role = rank_ladder.Current_Rank(SQL_Cursor, Caller)
	if Caller_Role is None:
		return "caller_no_rank", Details
	Details["caller_role"] = Caller_Role
	Caller_Rank_Id = rank_ladder.Rank_Id_For(SQL_Cursor, Caller_Role.id)
	if Caller_Rank_Id is None:
		return "caller_no_rank", Details
	if Direction == rank_ladder.DEMOTION:
		Subject_Rank_Id = rank_ladder.Rank_Id_For(SQL_Cursor, Subject_Role.id)
		if Subject_Rank_Id is None or Subject_Rank_Id >= Caller_Rank_Id:
			return "subject_not_below", Details
		return None, Details
	Target_Rank_Id = rank_ladder.Rank_Id_For(SQL_Cursor, Target_Role.id)
	if Target_Rank_Id is None or Caller_Rank_Id < Target_Rank_Id:
		return "rank_too_low", Details
	elif Caller_Rank_Id > Target_Rank_Id:
		return None, Details
	#Equal rank: the caller must have held it for the configured delay
	Wait_Days = bot_config.Get_Value_By_Name(SQL_Cursor, EQUAL_RANK_DELAY_CONFIG)
	if Wait_Days is None:
		return "config_missing", Details
	Wait_Days = int(Wait_Days)
	Details["wait_days"] = Wait_Days
	if Wait_Days <= 0:
		return None, Details
	Stored = sql_promotion.Member_Rank_Get(SQL_Cursor, Caller.id)
	if Stored is None or Stored["promotion_rank_id"] != Caller_Rank_Id:
		return "rank_sync_pending", Details
	Since = Stored["promotion_rank_updated_at"]
	if Since is None:
		return None, Details
	#Stored naive, UTC by convention (see poll_store.As_Aware)
	if Since.tzinfo is None:
		Since = Since.replace(tzinfo=datetime.timezone.utc)
	Until = Since + datetime.timedelta(days=Wait_Days)
	if datetime.datetime.now(datetime.timezone.utc) < Until:
		Details["until"] = Until
		return "equal_rank_wait", Details
	return None, Details
