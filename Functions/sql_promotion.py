# Raw SQL for the promotion rules and automatic promotions (see promotion_rules.py
# and Commands/promotions.py for the logic built on top of these).

from Functions import sql_config

#Whether promotion onto a rank is applied automatically once its vote passes.
#None if the rank doesn't exist
def Rank_Automatic_Promotion_Get(SQL_Cursor, Promotion_Rank_Id):
	if Promotion_Rank_Id is None:
		return None
	Query = "SELECT automatic_promotion FROM discord_promotion_ranks WHERE promotion_rank_id = %s"
	Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Promotion_Rank_Id,))
	if not Rows:
		return None
	return bool(Rows[0]["automatic_promotion"])

#A discord member's synced rank and when it last changed: {promotion_rank_id, promotion_rank_updated_at}
#promotion_rank_updated_at is NULL when the rank hasn't changed since tracking began. None if the member isn't known
def Member_Rank_Get(SQL_Cursor, Discord_Id):
	Query = "SELECT promotion_rank_id, promotion_rank_updated_at FROM discord_members WHERE discord_id = %s"
	Rows = sql_config.Query_Dicts_Get(SQL_Cursor, Query, (Discord_Id,))
	if not Rows:
		return None
	return Rows[0]
