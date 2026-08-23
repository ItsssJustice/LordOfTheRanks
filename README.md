# LordOfTheRanks

## Python version
- 3.14.7

## Required python packages
- python -m pip install python-dotenv
- python -m pip install discord
- python -m pip install mysql-connector-python

## Required .env file variables
| Field | Purpose |
|-------|---------|
| DISCORD_BOT_API_TOKEN | discord API bot token |
| DISCORD_GUILD | discord ID for the specific server |
| WOM_NAME | Discord name of the user connecting with the Wise Old Man API |
| WOM_API | Wise Old Man API bot token |
| MYSQL_HOST | Host address for the MySQL Server |
| MYSQL_USER | Username for the MySQL Server |
| MYSQL_PASS | Password for the MySQL Server |
## Polls

Two kinds, because they solve different problems.

### Native polls
Discord's own poll widget, via `discord.Poll`. Nice UI, discord handles expiry.
Requires discord.py >= 2.4.0.

| Command | Purpose | Access |
|---------|---------|--------|
| /pollcreate | Post a poll into a specific channel | everyone |
| /pollresults | Vote counts | everyone |
| /polldetailedresults | Who voted for what | Manage Roles |
| /pollend | Close a poll early | everyone |
| /pollgrant | Give a role to everyone who voted for one answer | Manage Roles |

**Native polls cannot be anonymised.** Discord's own client lets anyone click the
vote count and see the voter list, while running and after it ends. There is no
API flag or permission that changes this. Gating /polldetailedresults is a
convenience, not a confidentiality control.

### Secret ballots
Not a native poll: a message with buttons, where the votes are recorded by the
bot instead of by discord. Use when people must not be swayed by how others have
voted, for example a rank vote.

| Command | Purpose | Access |
|---------|---------|--------|
| /secretpoll | Post a ballot nobody can see the votes of | Manage Roles |
| /secretpollresults | Counts, sealed until the ballot closes | everyone |
| /secretpolldetailed | Who voted for what | Manage Roles |
| /secretpollend | Close early and publish the counts | Manage Roles |

Counts stay sealed while voting is open, including from staff, because seeing
"12 vs 2" pressures late voters just as much as seeing names does.

Expiry is enforced by this bot rather than by discord, via a task that checks
once a minute. If the bot is offline when a ballot expires it closes on the next
start-up instead. `SecretPolls.json` **is** the ballot box; discord holds no
copy of it, so it is gitignored and worth backing up.

## Poll API notes

Things that are easy to get wrong, all learned the hard way:

- Vote counts only refresh via `channel.fetch_message()`. A cached `Message`
  keeps whatever counts it had when it was first seen.
- `Poll.total_votes` is a property; `Poll.is_finalised()` is a method.
- `Poll.victor_answer` is only populated from the poll-result system message
  discord posts when a poll ends, so it is `None` on a fetched poll even when one
  answer clearly won. `Functions/poll_format.py` computes the winner from the
  vote counts instead, and handles ties.
- Discord does not guarantee precise counts until a poll finalises: *"due to the
  intricacies of counting at scale, while a poll is in progress the results may
  not be perfectly accurate."* /pollgrant therefore refuses to run on an open
  poll unless explicitly overridden.
- Bots need the **Create Polls** permission to send a native poll, and **Manage
  Roles** (with their own role dragged above the target) for /pollgrant.
