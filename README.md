# LordOfTheRanks

## Python version
- 3.14.7

## Required python packages
- python -m pip install python-dotenv
- python -m pip install discord
- python -m pip install mysql-connector-python
- python -m pip install wom.py

## Required .env file variables
| Field | Purpose |
|-------|---------|
| DISCORD_API_TOKEN | discord API bot token |
| DISCORD_USER | discord ID for the bot |
| DISCORD_GUILD | discord ID for the specific server |
| WOM_USER | Discord name of the user connecting with the Wise Old Man API |
| WOM_API_TOKEN | Wise Old Man API bot token |
| WOM_GUILD | Wise old man group ID |
| MYSQL_HOST | Host address for the MySQL Server |
| MYSQL_USER | Username for the MySQL Server |
| MYSQL_PASS | Password for the MySQL Server |
## Rank votes

Staff vote on moving a member up or down the clan ladder, and the bot applies
the result by swapping their rank role.

| Command | Purpose |
|---------|---------|
| /startpromotionvote | Open a vote on moving a member up the ladder |
| /startdemotionvote | Open a vote on moving a member down the ladder |
| /pollgrant | Apply a closed vote to the member it was about |
| /pollresults | The counts, once voting has closed |
| /polldetailedresults | The counts broken down by member |
| /pollend | Close a vote now and publish the counts |
| /pollcreate | A generic poll, unrelated to ranks |

### Opening a vote

```
/startpromotionvote label:bob-promo member:@Bob channel:#staff
```

The target rank is worked out from the member's current rank rather than typed
in, so a vote cannot propose something that is not a rank. Naming a `role` goes
there instead, for a promotion that skips a step; it still has to be on the
ladder and in the direction the command implies. Someone at the top of the
ladder cannot be promoted, someone at the bottom cannot be demoted, and a member
holding no rank at all is refused - each with a reason rather than an empty vote.

Both answers name the rank they lead to and carry that rank's emote, so the
posted vote reads:

```
Promote Bob from Sergeant to Cadet?

- Yes - Cadet
- No - stay Sergeant

Vote started by SomeStaffMember
```

Who started it is taken from the interaction rather than asked for.

### Applying a vote

```
/pollend   label:bob-promo
/pollgrant label:bob-promo
```

`/pollgrant` takes nothing but the label: who the vote was about, which rank was
proposed and which rank they held are all recorded on the vote. It reads the
result and, if Yes won outright, makes the change. A loss, a tie or an empty
vote stops it and reports the tally; `force:True` overrides.

For a rank vote this is a *change*: the new rank is added and the old one
removed, since ladder ranks are exclusive. `apply` defaults to off, so the first
run is a dry run naming exactly who would gain and lose what. It acts on the
**subject**, never on the people who voted.

Applying a vote records that it happened, so it drops out of the list and cannot
be applied twice by accident.

### The rank ladder

`Functions/rank_ladder.py` holds the progression, highest first, matched to
roles by name:

```
Owner, Deputy Owner, General, Captain, Lieutenant, Trialist,
Astral, Colonel, Cadet, Sergeant, Corporal, Recruit, Infantry
```

Discord's own role `position` is deliberately not used to infer order, since it
interleaves ranks with colour, ping and bot roles. At start-up the bot prints
the ladder against the server's real roles and warns about any name it cannot
find.

**This module is meant to be replaced.** Everything else asks it four questions -
what rank does this member hold, what is one step up or down, is a hand-picked
target sensible, and what is a rank's emote - and nothing outside it knows how
the order is decided. Swapping the list for a lookup against the members table
moves the source of truth into SQL without touching a single command.

### How the votes are stored

These are not discord's native polls. A native poll's voter list is shown to
anyone who clicks it and cannot be hidden, which is no good for a rank vote
where people should not be swayed by how others voted. Instead the bot posts a
message with buttons: a click is an interaction only this bot sees, and the vote
is written to `Polls.json`.

Consequences, all deliberate:

* Counts are sealed until voting closes.
* Duration is enforced by the bot, via a task that checks once a minute. If the
  bot is offline when a vote expires it closes on the next start-up instead.
* Buttons survive a restart because each carries a `custom_id` of
  `poll:<key>:<index>`, and `on_ready` re-registers a view for every open vote.
* `Polls.json` **is** the ballot box. Discord holds no copy, so it is gitignored
  and worth backing up.

### Permissions

The bot needs **Manage Roles**, and its own role must sit above every rank it
will assign *and* remove. **Use External Emojis** is needed for rank emotes to
render in the vote text; buttons show them regardless.
