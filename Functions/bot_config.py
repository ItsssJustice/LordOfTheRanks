#Get an env variable including required imports, for use inside functions to reduce duplicated imports
def env_get(Variable):
	import os
	import json
	return str(os.getenv(Variable))

class Message_Group:
	"""
	Tracks a set of related messages sent for a single interaction so that
	content exceeding Discord's 2000 character limit can be split across
	multiple messages, then later edited or deleted together as a group.
	"""

	MAX_LENGTH = 1900  # Headroom under Discord's 2000 character hard limit

	def __init__(self, interaction: discord.Interaction, ephemeral: bool = False):
		self.interaction = interaction
		self.ephemeral = ephemeral
		self.message_ids: list[int] = []

	@staticmethod
	def Split_Content(content: str, max_length: int = MAX_LENGTH) -> list[str]:
		"""
		Splits content into chunks no longer than max_length, breaking on
		newline boundaries where possible. Falls back to a hard split only
		if a single line itself exceeds max_length.
		"""
		if len(content) <= max_length:
			return [content]

		chunks = []
		current_lines = []
		current_length = 0

		for line in content.split("\n"):
			line_length = len(line) + 1  # +1 for the newline that joins lines back together

			if line_length > max_length:
				if current_lines:
					chunks.append("\n".join(current_lines))
					current_lines = []
					current_length = 0
				for i in range(0, len(line), max_length):
					chunks.append(line[i:i + max_length])
				continue

			if current_length + line_length > max_length:
				chunks.append("\n".join(current_lines))
				current_lines = [line]
				current_length = line_length
			else:
				current_lines.append(line)
				current_length += line_length

		if current_lines:
			chunks.append("\n".join(current_lines))

		return chunks

	async def Send(self, content: str, view: discord.ui.View = None) -> list[int]:
		"""
		Sends content as one or more followup messages, splitting as needed,
		and records the resulting message IDs. The view (if provided) is
		only attached to the final message in the group. Defers the
		interaction's initial response first if it hasn't been responded to,
		so every message in the group is a followup and can later be
		edited/deleted uniformly by ID.
		"""
		if not self.interaction.response.is_done():
			await self.interaction.response.defer(ephemeral=self.ephemeral)

		self.message_ids = []
		chunks = self.Split_Content(content)

		for index, chunk in enumerate(chunks):
			is_last = index == len(chunks) - 1
			sent_message = await self.interaction.followup.send(
				chunk, view=view if is_last else None, ephemeral=self.ephemeral, wait=True
			)
			self.message_ids.append(sent_message.id)

		return self.message_ids

	async def Edit(self, content: str, view: discord.ui.View = None) -> list[int]:
		"""
		Re-splits content and edits the existing group's messages to match.
		Sends extra messages if the new content needs more chunks than
		before, and deletes leftover messages if it needs fewer. The view
		(if provided) is only attached to the final message in the group.
		"""
		if not self.message_ids:
			return await self.Send(content, view=view)

		chunks = self.Split_Content(content)
		updated_ids = []

		for index, chunk in enumerate(chunks):
			is_last = index == len(chunks) - 1
			chunk_view = view if is_last else None

			if index < len(self.message_ids):
				message_id = self.message_ids[index]
				try:
					await self.interaction.followup.edit_message(message_id, content=chunk, view=chunk_view)
					updated_ids.append(message_id)
				except discord.NotFound:
					sent_message = await self.interaction.followup.send(chunk, view=chunk_view, ephemeral=self.ephemeral, wait=True)
					updated_ids.append(sent_message.id)
			else:
				sent_message = await self.interaction.followup.send(chunk, view=chunk_view, ephemeral=self.ephemeral, wait=True)
				updated_ids.append(sent_message.id)

		if len(self.message_ids) > len(chunks):
			for message_id in self.message_ids[len(chunks):]:
				try:
					await self.interaction.followup.delete_message(message_id)
				except discord.NotFound:
					pass

		self.message_ids = updated_ids
		return self.message_ids

	async def Delete(self) -> None:
		"""Deletes every message currently tracked in this group."""
		for message_id in self.message_ids:
			try:
				await self.interaction.followup.delete_message(message_id)
			except discord.NotFound:
				pass
		self.message_ids = []

#Displays an error due to command permissions
async def Command_Permissions_Issue(interaction, Display_Message = True):
	from Functions import embed_handling
	import discord
	Message = "You do not have the correct permissions execute this command with the inputs supplied. Please contact a moderator if you believe this is incorrect."
	Embed = embed_handling.Build(
		title="Command Failed",
		description=Message,
		colour=discord.Colour.red()
	)
	if Display_Message:
		await embed_handling.Send(interaction, Embed, ephemeral=True)
		return None
	return Message

#Log channel
async def Notify_Channel(client, Channel_ID = None, Message = None):
	"""Send a plain notification message to a channel by id, best-effort."""
	if Message is None:
		return
	if not Channel_ID:
		return
	try:
		Channel_ID = int(Channel_ID)
	except (TypeError, ValueError):
		return
	Channel = client.get_channel(Channel_ID)
	if Channel is None:
		try:
			Channel = await client.fetch_channel(Channel_ID)
		except Exception:
			return
	try:
		await Channel.send(Message)
	except Exception:
		return