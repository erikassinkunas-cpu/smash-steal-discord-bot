# Community V2

## Features

The existing `suggestions` channel accepts a new text message, `/suggest text:...`, or the persistent Submit suggestion button. The bot publishes a separate voting card with a per-kind SUG number. Original messages are preserved. Replies to messages are discussions, not new suggestions. Existing historical messages are not imported automatically.

Suggestions require 10 to 1600 characters and have a persisted 60-second author cooldown. Each verified Member has one vote per suggestion, can switch between Support/Oppose, or remove it. Staff use `/suggest-accept suggestion_id:SUG-001 reason:...`, `/suggest-deny`, and `/suggest-planned`. Decisions update the same card, close voting, preserve counts, and are recorded in SQLite and the existing moderation log. An accepted/planned idea does not promise a release date.

Staff create polls in `polls-and-events` with `/poll question:... options:Option A | Option B | Option C hours:24`. Polls allow 2 to 10 distinct options, each up to 80 characters. Questions contain 5 to 200 characters. Duration is 1 to 168 hours; default 24. A persisted 10-second creation cooldown applies. Members can cast, change or remove one vote. `/poll-close poll_id:POLL-001 reason:...` closes a poll early. Expired polls reject votes immediately even before the display refreshes. Deadlines are checked after restart. Totals refresh in the 5-second maintenance cycle.

`/community-status` reports stored item/vote counts, pending display updates and SQLite integrity. Status changes, poll creation and closure enforce the existing server-team check at execution time, independently of Discord's default slash-command visibility. Pending/unverified accounts and bots cannot vote.

## Storage

Attach a Railway volume to the existing bot service at `/data`. Community state is stored in `/data/community.sqlite3`, using WAL and transactions. No extra database service or public endpoint is used. Voter IDs are stored to enforce one vote per account; displayed cards expose only counts. Database access remains limited to the hosting workspace. Do not commit database files or publish them.

On Railway, the extension refuses to initialise without `RAILWAY_VOLUME_MOUNT_PATH`, rather than silently storing votes on ephemeral disk. Locally, set `COMMUNITY_DATA_DIR` or use `./data`. Existing secrets are read by the original bot and never copied into these files.

Discord messages that are manually deleted are not automatically reposted. A database record that was saved but not published is retried. Recovery inspects the latest 100 channel messages for the exact bot-owned item marker. This handles common interrupted-send cases; it is not a transactional guarantee across Discord and SQLite under arbitrary failures.

## Integration and deployment

`bot.py` is the existing legacy script. `integrate_community.py` makes one guarded, idempotent build-time insertion before its final `bot.run` call. It adds `install_community(globals())` and enables normal library logging. It does not rewrite existing roles, permissions, tickets or moderation handlers. The extension preserves original setup, ready and message callbacks.

The root `railway.json` runs integration, all tests with discord.py required, syntax compilation, and starts `python -u bot.py`. This design keeps the legacy source untouched in Git while making the deployed integration reproducible and separately reviewable. Run `python integrate_community.py` before `python bot.py` for local use.

## Tests and limits

Run `REQUIRE_DISCORD_TESTS=1 python -m unittest discover -s tests -v` in an environment with the repository requirements installed. Tests cover persistence, cooldowns, simultaneous writes, vote changes/removal, source replay, wrong-guild/message rejection, deadlines, status locking, role access guards, component layouts and command registration. Tests use temporary databases and never contact Discord.

Startup logs and the existing server audit verify configuration, not a human end-to-end click. Validate in Discord by submitting an idea, changing/removing a vote, marking it Planned, and creating/closing a poll. The new module does not claim to fix or fully test unrelated legacy moderation/ticket behavior.
