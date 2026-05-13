# Security review of imported files

Checked local files that were present before the new project scaffold:

- `legacy/userbot_unsafe_reference.py.txt`
- `legacy/ВАЖНО!!!.txt`

Findings:

- No reverse shell, remote command execution, `subprocess`, `os.system`, raw sockets, or remote code loading were found.
- The old script is not safe as an application baseline:
  - secrets are intended to be hardcoded in source;
  - `BOT_TOKEN` is referenced but not defined, while `token` exists;
  - it uses a root-level Telethon session name that could create `ub.session`;
  - `.spam` allows up to 20 repeated messages;
  - `.mute` deletes messages from muted users in Telegram, not only inside the project;
  - texts are mojibake and include an external promotional Telegram link.

Decision:

- The file is kept only as a quarantined text reference and is not imported by the new app.
- The new project implements a safe `.repeat` with `MAX_REPEAT_COUNT=5` by default, hard cap `10`, current-chat-only behavior, and cooldown instead of mass spam tooling.
