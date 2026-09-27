# Keeping the bot connected to Discord.
#
# discord.py already reconnects its gateway by itself (Client.start(reconnect=True)
# retries dropped connections with backoff, resuming the session where it can).
# What it does NOT retry is anything that makes Client.start raise: most often
# the login request at startup failing because the network or Discord's API is
# down, or a fatal gateway close. Before this, Discord_Client.run() then returned,
# and the bot's process quietly ended.
#
# Run_Forever is used in place of Discord_Client.run(). It runs the client and,
# whenever start() raises, closes it, waits (5s, doubling each time up to 5
# minutes; a connection that stayed up for DISCORD_STABLE_SECONDS resets the
# wait), resets the client and starts it again. It only gives up on errors a
# restart can't fix - a bad token (LoginFailure) or intents the bot hasn't been
# granted (PrivilegedIntentsRequired) - and stops cleanly if the client is
# closed on purpose.
#
# Restarting a client clears its cache and its persistent views, and fires
# on_ready again - see on_ready in LordOfTheRanks.py for what runs once and
# what runs on every ready. The background loops (poll closer, scheduler) run on
# the asyncio loop rather than the client, so they carry on across a restart and
# pause while the client isn't ready.

import asyncio
import time
import discord

DISCORD_RECONNECT_DELAY_MIN = 5
DISCORD_RECONNECT_DELAY_MAX = 300
DISCORD_STABLE_SECONDS = 600

def _Reset_Client(Client):
	"""Make a closed client startable again. clear() resets its state, but its HTTP
	connection pool was closed along with the client, and discord.py would reuse it."""
	Client.clear()
	Connector = getattr(Client.http, "connector", discord.utils.MISSING)
	if Connector is not discord.utils.MISSING and Connector.closed:
		Client.http.connector = discord.utils.MISSING

async def Run_Forever(Client, Token):
	Delay = DISCORD_RECONNECT_DELAY_MIN
	try:
		while True:
			Started = time.monotonic()
			try:
				await Client.start(Token, reconnect=True)
				#start() only returns once the client has been closed on purpose
				print("Discord : client closed, not reconnecting")
				return
			except (discord.LoginFailure, discord.PrivilegedIntentsRequired) as Error:
				print("Discord : %r - fix the bot's token/intents, a restart won't help" % Error)
				raise
			except Exception as Error:
				print("Discord : connection failed: %r" % Error)
			if not Client.is_closed():
				await Client.close()
			if time.monotonic() - Started >= DISCORD_STABLE_SECONDS:
				Delay = DISCORD_RECONNECT_DELAY_MIN
			print("Discord : reconnecting in %d second(s)" % Delay)
			await asyncio.sleep(Delay)
			Delay = min(Delay * 2, DISCORD_RECONNECT_DELAY_MAX)
			_Reset_Client(Client)
	finally:
		if not Client.is_closed():
			await Client.close()

async def Wait_Until_Connected(Client, Poll_Seconds=5):
	"""For background loops: return once the client is connected and ready,
	waiting through any restart Run_Forever is doing."""
	while Client.is_closed() or not Client.is_ready():
		await asyncio.sleep(Poll_Seconds)
