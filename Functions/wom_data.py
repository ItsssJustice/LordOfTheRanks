# Import core libraries
import os
import importlib
import asyncio
import datetime
import dotenv
import json
import discord
import wom
import mysql.connector

#Connect to WOM
async def Connect(WOM_USER="", WOM_TOKEN="", WOM_URL="https://api.wiseoldman.net/v2"):
	#Initiate WOM client
	print("WOM : Connecting to WOM")
	Connected = True
	WOM_Client = wom.Client()
	try:
		await WOM_Client.start()
		#Set API variables
		
		#WOM_Client.set_api_base_url(WOM_URL)
		if isinstance(WOM_TOKEN, str) and WOM_TOKEN.strip():
			print(f"WOM : Setting API key {WOM_TOKEN}")
			WOM_Client.set_api_key(WOM_TOKEN)
		if isinstance(WOM_USER, str) and WOM_USER.strip():
			print(f"WOM : Setting API user {WOM_USER}")
			WOM_Client.set_user_agent(WOM_USER)
		print(WOM_Client)
	except:
		Connected = False
	''' NOT SURE WHY CAN'T VERIFY THAT API KEY IS IN USE BUT I'LL LEAVE THIS HERE FOR NOW ANYWAYS JUST IN CASE I GET BORED AND COME BACK TO THIS LATER (IF I REMEMBER)
	Session = WOM_Client._http._session
	sent_key = Session.headers.get("x-api-key")
	sent_agent = Session.headers.get("User-Agent")

	#Send a single request to verify ratelimits are applied (etc)
	async with Session.get(WOM_URL+"/players/search", params={"username": "itsssjustice"}, headers={"x-api-key": WOM_TOKEN}) as resp:
		Sent_Key = resp.request_info.headers.get("x-api-key")
		if Sent_Key == WOM_TOKEN:
			print("\n[OK] Request actually carried your API key.")
		else:
			print(f"\n[FAIL] Request did NOT carry your API key (got: {Sent_Key!r}).")
		headers = resp.headers

		limit = resp.headers.get("RateLimit-Limit")
		remaining = resp.headers.get("RateLimit-Remaining")
		reset = resp.headers.get("RateLimit-Reset")
		status = resp.status
		response = await resp.read()

	for header in headers:
		print(f"{header}: {headers[header]}\r\n".encode("latin-1"))
	print(response)
	print(f"\nResponse status: {status}")
	print(f"RateLimit-Limit:     {limit}")
	print(f"RateLimit-Remaining: {remaining}")
	print(f"RateLimit-Reset:     {reset}s")

	if limit is None:
		print(
			"\n[WARN] No RateLimit-Limit header returned -- can't confirm "
			"the tier from this response."
		)
	elif limit == "100":
		print("\n[OK] Limit is 100/60s -- the API key is granting the elevated tier.")
	elif limit == "20":
		print(
			"\n[FAIL] Limit is 20/60s -- you're still on the default tier. "
			"Double check the key is valid/active on WOM's end."
		)
	else:
		print(f"\n[INFO] Limit is {limit}/60s -- unexpected value, but not the default 20.")
		'''
	return [WOM_Client, Connected]

#Disconnect from WOM
async def Disconnect(WOM_Client):
	# Close the client
	await WOM_Client.close()

async def Members_Get(WOM_USER, WOM_TOKEN, WOM_GUILD):
	print(f"WOM : Retriving members for group {WOM_GUILD}")
	[WOM_Client, Connected] = await Connect(WOM_USER, WOM_TOKEN)
	Member_Data = {}
	try:
		if Connected:
			result = await WOM_Client.groups.get_details(WOM_GUILD)
			if not result.is_ok:
				raise Exception(f"Failed to retrieve group details: {result}")
			# original data here
			group = result.unwrap()
			# create new JSON structure
			Member_Data = {
				"groupData": {
					"id": group.id,
					"name": group.name,
					"member_count": group.member_count,
					"memberships": [
						{
							"player_id": membership.player_id,
							"display_name": membership.player.display_name,
							"role": membership.role.value,
							"created_at": membership.created_at.isoformat()
						}
						for membership in group.memberships
					]
				}
			}
		return Member_Data
	finally:
		await Disconnect(WOM_Client)

def Members_Display(Member_Data):
	group = Member_Data["groupData"]
	if not group:
		print("No group found.")
		return
	group_members = group["memberships"]
	if not group_members:
		print("No group members found.")
		return
	print()
	print(f"Group:        {group['name']}")
	print(f"ID:           {group['id']}")
	print(f"Member count: {group['member_count']}")
	print()
	print(
		f"{'Player ID':<12}"
		f"{'Display Name':<25}"
		f"{'Role':<15}"
		f"{'Joined':<30}"
	)
	print("-" * 82)
	for membership in group_members:
		print(
			f"{membership['player_id']:<12}"
			f"{membership['display_name']:<25}"
			f"{membership['role']:<15}"
			f"{membership['created_at']:<30}"
		)

async def Namechanges_Get(WOM_USER, WOM_TOKEN, WOM_GUILD, LIMIT):
	print(f"WOM : Retriving name changes for group {WOM_GUILD}")
	[WOM_Client, Connected] = await Connect(WOM_USER, WOM_TOKEN)
	Namechange_Data = {}
	try:
		if Connected:
			result = await WOM_Client.groups.get_name_changes(WOM_GUILD, limit=LIMIT)
			if not result.is_ok:
				raise Exception(f"Failed to retrieve group details: {result}")
			# original data here
			changes = result.unwrap()
			# create new JSON structure
			Namechange_Data = {
				"nameChanges": [
					{
						"id": change.id,
						"player_id": change.player_id,
						"old_name": change.old_name,
						"new_name": change.new_name,
						"created_at": change.created_at.isoformat()
					}
					for change in changes
				]
			}
		return Namechange_Data
	finally:
		await Disconnect(WOM_Client)

def Namechanges_Display(Namechange_Data):
	changes = Namechange_Data["nameChanges"]
	if not changes:
		print("No name changes found.")
		return
	print()
	print(f"Latest {len(changes)} name changes")
	print()
	print(
		f"{'ID':<10}"
		f"{'Player ID':<12}"
		f"{'Old Name':<25}"
		f"{'New Name':<25}"
		f"{'Created At':<30}"
	)
	print("-" * 102)
	for change in changes:
		print(
			f"{change['id']:<10}"
			f"{change['player_id']:<12}"
			f"{change['old_name']:<25}"
			f"{change['new_name']:<25}"
			f"{change['created_at']:<30}"
		)

#How many of the group's competitions to ask WOM for per page, and how many pages to look through
#when finding the latest finished one (50 per page is WOM's own maximum)
COMPETITION_PAGE_SIZE = 50
COMPETITION_PAGE_LIMIT = 20

def _As_UTC(Value):
	"""WOM datetimes as timezone-aware UTC, whether or not they arrive with a timezone."""
	if Value.tzinfo is None:
		return Value.replace(tzinfo=datetime.timezone.utc)
	return Value.astimezone(datetime.timezone.utc)

async def _Latest_Finished_Competition_Id(WOM_Client, WOM_GUILD):
	"""The id of the group's competition that ended most recently (and has ended), or None."""
	Now = datetime.datetime.now(datetime.timezone.utc)
	Latest = None
	for Page in range(COMPETITION_PAGE_LIMIT):
		result = await WOM_Client.groups.get_competitions(int(WOM_GUILD), limit=COMPETITION_PAGE_SIZE, offset=Page * COMPETITION_PAGE_SIZE)
		if not result.is_ok:
			raise Exception(f"Failed to retrieve competitions: {result}")
		competitions = result.unwrap()
		for competition in competitions:
			Ends_At = _As_UTC(competition.ends_at)
			if Ends_At <= Now and (Latest is None or Ends_At > _As_UTC(Latest.ends_at)):
				Latest = competition
		if len(competitions) < COMPETITION_PAGE_SIZE:
			break
	return Latest.id if Latest else None

async def Competition_Get(WOM_USER, WOM_TOKEN, WOM_GUILD, WOM_COMPETITION_ID=None, Contribution_Threshold = 0):
	"""A homeland competition's details and qualifying participants.

	With WOM_COMPETITION_ID, that competition - which must belong to the WOM_GUILD
	group. Without one (None or 0), the group's competition that finished most recently.

	Returns {"competition": {...} or None, "error": code}, where code is:
	  None                 found - "competition" holds it (its "finished" says whether it has ended)
	  "wom_unavailable"    WOM couldn't be reached, or answered with an error
	  "not_found"          WOM has no competition with that id
	  "not_in_group"       the competition exists but isn't the homeland group's
	  "none_finished"      no id given, and the group has no finished competition
	"""
	if WOM_COMPETITION_ID:
		print(f"WOM : Retrieving competition {WOM_COMPETITION_ID}")
	else:
		print(f"WOM : Retrieving latest finished competition for group {WOM_GUILD}")
	[WOM_Client, Connected] = await Connect(WOM_USER, WOM_TOKEN)
	Competition_Data = {"competition": None, "error": None}
	try:
		if not Connected:
			Competition_Data["error"] = "wom_unavailable"
			return Competition_Data
		try:
			if WOM_COMPETITION_ID:
				# use the specific competition id provided
				competition_id = WOM_COMPETITION_ID
			else:
				competition_id = await _Latest_Finished_Competition_Id(WOM_Client, WOM_GUILD)
				if competition_id is None:
					Competition_Data["error"] = "none_finished"
					return Competition_Data
			# get details from comp
			details_result = await WOM_Client.competitions.get_details(int(competition_id))
		except Exception as Error:
			print(f"WOM : Competition lookup failed: {Error!r}")
			Competition_Data["error"] = "wom_unavailable"
			return Competition_Data
		if not details_result.is_ok:
			print(f"WOM : Failed to retrieve competition {competition_id}: {details_result}")
			Competition_Data["error"] = "not_found"
			return Competition_Data
		# original call output
		details = details_result.unwrap()
		# Only the homeland clan's own competitions can be paid out
		if details.group_id is None or int(details.group_id) != int(WOM_GUILD):
			print(f"WOM : Competition {details.id} belongs to group {details.group_id}, not {WOM_GUILD}")
			Competition_Data["error"] = "not_in_group"
			return Competition_Data
		# filter for only participants with XP gained
		participants = sorted(
			(
				p for p in details.participations
				if p.progress.gained > Contribution_Threshold
			),
			key=lambda p: p.progress.gained,
			reverse=True
		)
		# create JSON structure
		Competition_Data["competition"] = {
			"competition_id": details.id,
			"group_id": details.group_id,
			"title": details.title,
			"starts_at": details.starts_at.isoformat(),
			"ends_at": details.ends_at.isoformat(),
			"finished": _As_UTC(details.ends_at) <= datetime.datetime.now(datetime.timezone.utc),
			"metric": details.metric.value,
			"results": [
				{
					"player_id": participant.player_id,
					"display_name": participant.player.display_name,
					"gained": participant.progress.gained
				}
				for participant in participants
			]
		}
		return Competition_Data
	finally:
		await Disconnect(WOM_Client)

def Competition_Display(Competition_Data):
	competition = Competition_Data["competition"]
	if not competition:
		print("No competition found.")
		return
	results = competition["results"]
	if not results:
		print("No results found.")
		return
	print()
	print(f"Competition: {competition['title']}")
	print(f"ID:         {competition['competition_id']}")
	print(f"Starts at:  {competition['starts_at']}")
	print(f"Ends at:    {competition['ends_at']}")
	print(f"Metric:     {competition['metric']}")
	print()
	print(
		f"{'Rank':<8}"
		f"{'Player ID':<12}"
		f"{'Display Name':<25}"
		f"{'Gained':>12}"
	)
	print("-" * 57)
	for rank, result in enumerate(results, start=1):
		print(
			f"{rank:<8}"
			f"{result['player_id']:<12}"
			f"{result['display_name']:<25}"
			f"{result['gained']:>12}"
		)

async def Activities_Get(WOM_USER, WOM_TOKEN, WOM_GUILD, LIMIT):
	print(f"WOM : Retriving name changes for group {WOM_GUILD}")
	[WOM_Client, Connected] = await Connect(WOM_USER, WOM_TOKEN)
	Activity_Data = {}
	try:
		if Connected:
			# get latest 50 activities
			result = await WOM_Client.groups.get_activity(
				WOM_GUILD,
				limit=LIMIT
			)

			if not result.is_ok:
				print("Failed to retrieve group activities:")
				print(result)
				return None

		# Original output here in results.unwrap()
			activities = result.unwrap()

			# filter and restructure JSON
			Activity_Data = {
				"activities": [
					{
						"group_id": activity.group_id,
						"player_id": activity.player_id,
						"display_name": activity.player.display_name,
						"type": activity.type.value,
						"role": activity.role.value if activity.role else None,
						"created_at": activity.created_at.isoformat()
					}
					for activity in activities
					if activity.type.value in (
						"joined",
						"left",
						"changed_role"
					)
				]
			}
		return Activity_Data
	finally:
		await Disconnect(WOM_Client)

def Activities_Display(Activity_Data):
	activities = Activity_Data["activities"]
	if not activities:
		print("No activities found.")
		return
	print()
	print(f"Group activities: {len(activities)}")
	print()
	print(
		f"{'Type':<15}"
		f"{'Player ID':<12}"
		f"{'Display Name':<25}"
		f"{'Role':<15}"
		f"{'Created At':<30}"
	)
	print("-" * 97)
	for activity in activities:
		print(
			f"{activity['type']:<15}"
			f"{activity['player_id']:<12}"
			f"{activity['display_name']:<25}"
			f"{str(activity['role']):<15}"
			f"{activity['created_at']:<30}"
		)

async def main():
	LIMIT = 50
	#Load environment variables from external file
	dotenv.load_dotenv()
	#WOM connection environment variables
	WOM_USER = str(os.getenv("WOM_USER"))
	WOM_TOKEN = str(os.getenv("WOM_API_TOKEN"))
	WOM_GUILD = os.getenv("WOM_GUILD")
	#Member_Data = await Members_Get(WOM_USER, WOM_TOKEN, WOM_GUILD)
	#Members_Display(Member_Data)
	#Namechange_Data = await Namechanges_Get(WOM_USER, WOM_TOKEN, WOM_GUILD, LIMIT)
	#Namechanges_Display(Namechange_Data)
	Competition_Data = await Competition_Get(WOM_USER, WOM_TOKEN, WOM_GUILD)
	Competition_Display(Competition_Data)
	Activity_Data = await Activities_Get(WOM_USER, WOM_TOKEN, WOM_GUILD, LIMIT)
	Activities_Display(Activity_Data)


if __name__ == "__main__":
	asyncio.run(main())