import discord
# ---------------------------------------------------------------------------
# Embed building, pagination (via discord.ui.View buttons) and send/update/delete.
#
# Build never raises over a character-limit problem - discord's limits
# (256 title, 4096 description, 256/1024 per field, 6000 total, 25 fields) are
# checked here first, anything too long is trimmed and the trim is printed to
# console so it's visible without the caller having to check for it.
#
# Embed_Paginate turns a long field list into several embeds; hand that list
# to Send and it becomes an Embed_Paginator_View (Previous/Stop/Next
# buttons) instead of a single message.
#
# Both Send paths accept an optional `extra_buttons` list so a command
# can add its own buttons alongside the built-in navigation. This module only
# renders those buttons and dispatches their clicks - it has no idea what any
# of them actually do. Each entry is a dict:
#   {"label": str, "emoji": str, "style": discord.ButtonStyle,
#    "row": int, "callback": async def(interaction, view)}
# or, for a link button that opens a URL without ever reaching the bot:
#   {"label": str, "emoji": str, "style": discord.ButtonStyle.link, "url": str}
# All keys except one of "callback"/"url" are optional.
#
# On a paginated (Embed_Paginator_View) message, a spec may also carry
# "cancel": True. That entry REPLACES the built-in Stop button in place - same
# position, same row - rather than being appended as an extra item. Its own
# callback then runs instead of the default stop/delete behaviour, and is
# responsible for calling view.stop() itself if the view should stop reacting
# to further clicks. Only the first "cancel"-marked spec in the list is used;
# this has no special meaning on a non-paginated Embed_Button_View, which has
# no Stop button to replace.
#
# The behaviour behind a callback button belongs entirely to whoever built the
# button list - see Commands/points.py for a worked example.
#
# Update/Delete take either a plain discord.Message or the
# Embed_Paginator_View/Embed_Button_View handed back by Send, so the
# caller doesn't need to remember which kind they're holding.
# ---------------------------------------------------------------------------

EMBED_LIMIT_TITLE = 256
EMBED_LIMIT_DESCRIPTION = 4096
EMBED_LIMIT_FIELD_NAME = 256
EMBED_LIMIT_FIELD_VALUE = 1024
EMBED_LIMIT_FOOTER = 2048
EMBED_LIMIT_AUTHOR_NAME = 256
EMBED_LIMIT_FIELDS = 25
EMBED_LIMIT_TOTAL = 6000

#Trim a piece of embed text to a limit, printing to console when it had to cut anything.
def _Embed_Trim(Text, Limit, Field_Label):
	if Text is None:
		return None
	Text = str(Text)
	if len(Text) <= Limit:
		return Text
	print("Build : '%s' was %d characters, trimmed to the %d character limit"
		  % (Field_Label, len(Text), Limit))
	return Text[:max(0, Limit - 1)].rstrip() + "…"

#The total visible character count discord counts towards the 6000 character embed limit.
def _Embed_Total_Length(Embed):
	Total = len(Embed.title or "") + len(Embed.description or "")
	Total += len(Embed.footer.text or "")
	Total += len(Embed.author.name or "")
	for Field in Embed.fields:
		Total += len(Field.name or "") + len(Field.value or "")
	return Total

#A single field, accepted as (name, value), (name, value, inline) or {"name":, "value":, "inline":}
def _Embed_Field_Parts(Field):
	if isinstance(Field, dict):
		return Field.get("name"), Field.get("value"), Field.get("inline", False)
	if len(Field) == 2:
		Name, Value = Field
		return Name, Value, False
	Name, Value, Inline = Field
	return Name, Value, Inline

#Build one discord.Embed, safely truncating anything that would breach discord's limits.
#fields is a list of (name, value), (name, value, inline) or {"name","value","inline"} entries.
#Never raises - a problem building the embed is printed to console and a stripped-down fallback
#embed is returned instead, so a bad title etc. never brings a command down.
def Build(title=None, description=None, colour=None, fields=None, footer=None,
				 author_name=None, author_icon_url=None, thumbnail_url=None, image_url=None,
				 url=None, timestamp=None):
	try:
		Embed = discord.Embed(
			title=_Embed_Trim(title, EMBED_LIMIT_TITLE, "title"),
			description=_Embed_Trim(description, EMBED_LIMIT_DESCRIPTION, "description"),
			colour=colour if colour is not None else discord.Colour(0x5865F2),
			url=url,
			timestamp=timestamp
		)
		if footer:
			Embed.set_footer(text=_Embed_Trim(footer, EMBED_LIMIT_FOOTER, "footer"))
		if author_name:
			Embed.set_author(name=_Embed_Trim(author_name, EMBED_LIMIT_AUTHOR_NAME, "author name"),
							  icon_url=author_icon_url)
		if thumbnail_url:
			Embed.set_thumbnail(url=thumbnail_url)
		if image_url:
			Embed.set_image(url=image_url)

		Fields = list(fields or [])
		if len(Fields) > EMBED_LIMIT_FIELDS:
			print("Build : %d fields supplied, discord allows %d per embed. The remaining "
				  "%d were dropped - use Embed_Paginate to spread them across pages instead."
				  % (len(Fields), EMBED_LIMIT_FIELDS, len(Fields) - EMBED_LIMIT_FIELDS))
			Fields = Fields[:EMBED_LIMIT_FIELDS]

		for Field in Fields:
			Name, Value, Inline = _Embed_Field_Parts(Field)
			#discord rejects an empty name/value outright, so fall back to a zero-width space
			Embed.add_field(
				name=_Embed_Trim(Name, EMBED_LIMIT_FIELD_NAME, "field name") or "​",
				value=_Embed_Trim(Value, EMBED_LIMIT_FIELD_VALUE, "field value") or "​",
				inline=bool(Inline)
			)

		Total = _Embed_Total_Length(Embed)
		if Total > EMBED_LIMIT_TOTAL and Embed.description:
			print("Build : embed totals %d characters, discord's overall limit is %d. "
				  "Trimming the description to make room." % (Total, EMBED_LIMIT_TOTAL))
			Overshoot = Total - EMBED_LIMIT_TOTAL
			New_Length = max(0, len(Embed.description) - Overshoot - 1)
			Embed.description = Embed.description[:New_Length].rstrip() + "…"

		return Embed
	except Exception as Error:
		print("Build : failed to build embed (%r), falling back to a plain error embed" % Error)
		return discord.Embed(title="⚠️ Error",
							  description="This message could not be displayed correctly. Check the console log.",
							  colour=discord.Colour.red())

#Split a long field list (and/or shared title/description/footer) into several embeds, each kept
#inside discord's per-embed field-count limit. Returns a list of discord.Embed for Send.
def Paginate(title=None, description=None, colour=None, fields=None, footer=None,
					fields_per_page=6, **Common_Kwargs):
	Fields = list(fields or [])
	if not Fields:
		return [Build(title=title, description=description, colour=colour,
							 footer=footer, **Common_Kwargs)]

	fields_per_page = max(1, min(fields_per_page, EMBED_LIMIT_FIELDS))
	Page_Count = -(-len(Fields) // fields_per_page)  # ceiling division
	Pages = []
	for Page_Index in range(Page_Count):
		Chunk = Fields[Page_Index * fields_per_page: (Page_Index + 1) * fields_per_page]
		if Page_Count > 1:
			Page_Footer = ("%s (page %d/%d)" % (footer, Page_Index + 1, Page_Count)
						   if footer else "Page %d/%d" % (Page_Index + 1, Page_Count))
		else:
			Page_Footer = footer
		Pages.append(Build(title=title, description=description, colour=colour,
								  fields=Chunk, footer=Page_Footer, **Common_Kwargs))
	return Pages

#Turn one extra-button spec into a real discord.ui.Button and wire it up.
#embed_handling has no idea what a callback does - it only calls it. A link-style button (or any
#button carrying a "url") is wired as a plain link instead: discord opens those client-side and
#never sends the bot an interaction, so it cannot carry a callback.
def _Build_Custom_Button(Spec, View):
	Style = Spec.get("style", discord.ButtonStyle.secondary)
	Url = Spec.get("url")
	if Url or Style == discord.ButtonStyle.link:
		return discord.ui.Button(
			label=Spec.get("label"), emoji=Spec.get("emoji"),
			style=discord.ButtonStyle.link, url=Url, row=Spec.get("row")
		)

	Button = discord.ui.Button(
		label=Spec.get("label"), emoji=Spec.get("emoji"),
		style=Style, row=Spec.get("row")
	)
	Callback = Spec.get("callback")

	async def _On_Click(interaction: discord.Interaction):
		if Callback is None:
			print("Embed_Handling : a button ('%s') was clicked with no callback supplied"
				  % (Spec.get("label") or Spec.get("emoji") or "?"))
			await interaction.response.defer()
			return
		try:
			await Callback(interaction, View)
		except Exception as Error:
			print("Embed_Handling : extra button callback raised: %r" % Error)
			if not interaction.response.is_done():
				await interaction.response.send_message(
					"Something went wrong handling that button, check the console log.",
					ephemeral=True)

	Button.callback = _On_Click
	return Button

#Pull the first "cancel": True spec out of a button-spec list, if there is one.
#Returns (Cancel_Spec_Or_None, Remaining_Specs).
def _Split_Cancel_Spec(Extra_Buttons):
	Cancel_Spec = None
	Remaining = []
	for Spec in (Extra_Buttons or []):
		if Cancel_Spec is None and Spec.get("cancel"):
			Cancel_Spec = Spec
		else:
			Remaining.append(Spec)
	return Cancel_Spec, Remaining

#A single embed with nothing but caller-supplied extra buttons attached - the non-paginated
#counterpart to Embed_Paginator_View. Only the person who triggered Send may use them.
#Has no built-in Stop button, so a "cancel"-marked spec here is treated as an ordinary button.
class Embed_Button_View(discord.ui.View):
	def __init__(self, Author_Id, Extra_Buttons=None, timeout=180):
		super().__init__(timeout=timeout)
		self.Author_Id = Author_Id
		self.message = None  # filled in by Send once the message exists
		for Spec in (Extra_Buttons or []):
			self.add_item(_Build_Custom_Button(Spec, self))

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.Author_Id:
			await interaction.response.send_message(
				"Only the person who ran this command can use these buttons.", ephemeral=True)
			return False
		return True

	async def on_timeout(self):
		for Item in self.children:
			Item.disabled = True
		if self.message is not None:
			try:
				await self.message.edit(view=self)
			except discord.HTTPException as Error:
				print("Embed_Button_View : could not disable buttons on timeout: %r" % Error)

#Previous/Stop/Next buttons over a list of pre-built embeds, plus any caller-supplied extra
#buttons appended after them. Only the person who triggered Send may operate any of them.
#
#If extra_buttons contains a spec marked "cancel": True, that spec REPLACES the Stop button in
#place (same row, same position) rather than being added alongside it - see the module docstring
#above. Built by hand rather than with @discord.ui.button, so that swap can be made cleanly
#without disturbing the Previous/Next ordering either side of it.
#Previous/Stop/Next buttons over a list of pre-built embeds, plus any caller-supplied extra
#buttons appended after them. Only the person who triggered Send may operate any of them.
#
#Standard left-to-right order is: Previous, Next, Cancel/Stop, then any remaining extra buttons
#in the exact order the caller supplied them.
#
#If extra_buttons contains a spec marked "cancel": True, that spec REPLACES the Stop button in
#place rather than being added as a further item - see the module docstring above. Built by hand
#rather than with @discord.ui.button, so the ordering can be controlled explicitly.
class Embed_Paginator_View(discord.ui.View):
	def __init__(self, Pages, Author_Id, Delete_On_Stop=True, Extra_Buttons=None, timeout=180):
		super().__init__(timeout=timeout)
		self.Pages = Pages
		self.Index = 0
		self.Author_Id = Author_Id
		self.Delete_On_Stop = Delete_On_Stop
		self.message = None  # filled in by Send once the message exists
		Cancel_Spec, Remaining_Extras = _Split_Cancel_Spec(Extra_Buttons)
		self.Previous_Button = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=0)
		self.Previous_Button.callback = self._On_Previous
		self.add_item(self.Previous_Button)
		self.Next_Button = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=0)
		self.Next_Button.callback = self._On_Next
		self.add_item(self.Next_Button)
		if Cancel_Spec is not None:
			self.Stop_Button = _Build_Custom_Button(Cancel_Spec, self)
			self.Stop_Button.row = 0
		else:
			self.Stop_Button = discord.ui.Button(label="Stop", style=discord.ButtonStyle.danger, row=0)
			self.Stop_Button.callback = self._On_Stop
		self.add_item(self.Stop_Button)
		self._Sync_Buttons()
		for Spec in Remaining_Extras:
			self.add_item(_Build_Custom_Button(Spec, self))

	def _Sync_Buttons(self):
		self.Previous_Button.disabled = (self.Index == 0)
		self.Next_Button.disabled = (self.Index == len(self.Pages) - 1)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.Author_Id:
			await interaction.response.send_message(
				"Only the person who ran this command can use these buttons.", ephemeral=True)
			return False
		return True

	async def _On_Previous(self, interaction: discord.Interaction):
		self.Index -= 1
		self._Sync_Buttons()
		await interaction.response.edit_message(embed=self.Pages[self.Index], view=self)

	#Default Stop behaviour - only ever wired up when no "cancel" spec replaced it.
	async def _On_Stop(self, interaction: discord.Interaction):
		self.stop()
		if self.Delete_On_Stop:
			try:
				await interaction.response.defer()
				await interaction.delete_original_response()
			except discord.HTTPException as Error:
				print("Embed_Paginator_View : could not delete paginated message: %r" % Error)
		else:
			for Item in self.children:
				Item.disabled = True
			await interaction.response.edit_message(view=self)

	async def _On_Next(self, interaction: discord.Interaction):
		self.Index += 1
		self._Sync_Buttons()
		await interaction.response.edit_message(embed=self.Pages[self.Index], view=self)

	async def on_timeout(self):
		#Buttons stop working once discord expires the view anyway; disabling them here just
		#makes that visible on the message instead of them silently doing nothing.
		for Item in self.children:
			Item.disabled = True
		if self.message is not None:
			try:
				await self.message.edit(view=self)
			except discord.HTTPException as Error:
				print("Embed_Paginator_View : could not disable buttons on timeout: %r" % Error)

	#Swap in a new set of pages without losing the message this view is attached to - e.g. a
	#status list that gets refreshed rather than reposted every time.
	async def Update_Pages(self, New_Pages):
		self.Pages = New_Pages
		self.Index = min(self.Index, len(New_Pages) - 1)
		self._Sync_Buttons()
		if self.message is not None:
			await self.message.edit(embed=self.Pages[self.Index], view=self)

#Send one embed, or a list of embeds as a paginated Embed_Paginator_View, in response to an
#interaction. Returns a discord.Message when there is a single page and no extra buttons, or an
#Embed_Button_View/Embed_Paginator_View otherwise - hand any of these straight back to
#Update / Delete later.
#
#extra_buttons: optional list of button specs (see the module docstring above), rendered
#alongside the built-in navigation on a paginated embed, or on their own for a single embed.
#embed_handling only wires the clicks through to each spec's own callback - it never decides
#what a button does.
async def Send(interaction, Embeds, ephemeral=False, extra_buttons=None, timeout=180):
	Pages = Embeds if isinstance(Embeds, list) else [Embeds]
	try:
		if len(Pages) == 1 and not extra_buttons:
			if interaction.response.is_done():
				return await interaction.followup.send(embed=Pages[0], ephemeral=ephemeral)
			await interaction.response.send_message(embed=Pages[0], ephemeral=ephemeral)
			return await interaction.original_response()

		if len(Pages) == 1:
			View = Embed_Button_View(interaction.user.id, Extra_Buttons=extra_buttons, timeout=timeout)
		else:
			View = Embed_Paginator_View(Pages, interaction.user.id,
										 Extra_Buttons=extra_buttons, timeout=timeout)

		if interaction.response.is_done():
			Message = await interaction.followup.send(embed=Pages[0], view=View, ephemeral=ephemeral)
		else:
			await interaction.response.send_message(embed=Pages[0], view=View, ephemeral=ephemeral)
			Message = await interaction.original_response()
		View.message = Message
		return View
	except discord.HTTPException as Error:
		print("Send : failed to send embed(s): %r" % Error)
		return None

#Edit an already-sent embed message (or the current page of a view) in place. Pass New_View to
#also replace the message's components in the same edit - e.g. after disabling buttons following
#a click, so the disabled state is pushed back to discord in one call.
async def Update(Message_Or_View, New_Embed, New_View=None):
	Target = (Message_Or_View.message
			  if isinstance(Message_Or_View, (Embed_Paginator_View, Embed_Button_View))
			  else Message_Or_View)
	try:
		if New_View is not None:
			await Target.edit(embed=New_Embed, view=New_View)
		else:
			await Target.edit(embed=New_Embed)
		return True
	except discord.HTTPException as Error:
		print("Update : failed to update embed message: %r" % Error)
		return False

#Delete an already-sent embed message (or a view's message). Already-gone and no-permission are
#both swallowed and logged rather than raised, since the caller usually can't act on either.
async def Delete(Message_Or_View):
	Target = (Message_Or_View.message
			  if isinstance(Message_Or_View, (Embed_Paginator_View, Embed_Button_View))
			  else Message_Or_View)
	try:
		await Target.delete()
		return True
	except discord.NotFound:
		return True
	except discord.Forbidden as Error:
		print("Delete : missing permission to delete embed message: %r" % Error)
		return False
	except discord.HTTPException as Error:
		print("Delete : failed to delete embed message: %r" % Error)
		return False