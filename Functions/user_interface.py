import discord

# Class for handling UI components of Points_WOM_Competition
class Add_WOM_Competition_Confirm(discord.ui.View):
	def __init__(self, interaction: discord.Interaction, Competition_Data: dict, contribution: dict, level: dict):
		super().__init__(timeout=120)
		self.original_interaction = interaction
		self.Competition_Data = Competition_Data

	async def on_timeout(self):
		# Disable buttons and let the moderator know the prompt expired
		for item in self.children:
			item.disabled = True
		try:
			await self.original_interaction.edit_original_response(content="Confirmation timed out, no points were added.", view=self,)
		except discord.NotFound:
			pass

	@discord.ui.button(label="Confirm", emoji="✅", style=discord.ButtonStyle.success)
	async def Confirm_Button(self, interaction: discord.Interaction, button: discord.ui.Button):
		# Only the moderator who ran the command can confirm
		if interaction.user.id != self.original_interaction.user.id:
			await interaction.response.send_message("Only the person who ran this command can confirm it.", ephemeral=True)
			return

		competition = self.Competition_Data["competition"]
		results = competition["results"]
		#Add points for competition data
		results = self.Competition_Data["competition"]["results"]
		if not results:
			return []
		participant_ids = [result["player_id"] for result in results]
		Linked_Accounts = sql_account_link.Linked_Accounts_Get(SQL_Cursor, player_id=participant_ids)
		discord_ids = [result["discord_id"] for result in discord_members]
		await points.Points_Adjust(interaction, contribution, level, discord_ids, other_points, True)

		for item in self.children:
			item.disabled = True
		await interaction.response.edit_message(content=f"✅ Points added for **{len(results)}** participants in **{competition['title']}**.",view=self,)
		self.stop()

	@discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger)
	async def Cancel_Button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id != self.original_interaction.user.id:
			await interaction.response.send_message("Only the person who ran this command can cancel it.", ephemeral=True)
			return
		for item in self.children:
			item.disabled = True
		await interaction.response.edit_message(content="❌ Points addition cancelled.",view=self,)
		self.stop()