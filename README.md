# Gmail attachments → Telegram (Docker)

Small Python service that polls Gmail over **IMAP**, downloads **new message attachments**, and posts **images** to a **Telegram channel** via **`sendPhoto`**. Non-image files are **skipped by default**; set **`SEND_DOCUMENT=true`** to also forward them with **`sendDocument`**. Message state is persisted on disk so restarts do not re-send old mail.

## What you need

- Gmail account with **IMAP enabled** and a **Google App Password** (2-Step Verification must be on).
- Telegram **bot token** and a **channel** where the bot can post (typically as an **administrator**).

## Quick start (Docker Compose)

1. Copy the environment template and fill secrets:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` (see variables in [`.env.example`](.env.example)).

3. Run:

   ```bash
   docker compose up --build -d
   ```

The compose file mounts a named volume at `/data` and sets `STATE_PATH=/data/state.json` for idempotent processing.

## Local run (without Docker)

Create a virtual environment, install dependencies, configure `.env`, then:

```bash
python -m app.main
```

Ensure `STATE_PATH` points to a writable file (for example `./data/state.json`).

## Gmail: enable IMAP and create an App Password

1. Open Google Account security: [Google Account → Security](https://myaccount.google.com/security).
2. Enable **2-Step Verification** if it is not already enabled (App Passwords require it).
3. Open **App passwords** (you may need to search for “App passwords” in your Google Account).
4. Create a new app password (for example “Mail” / “Other”) and copy the 16-character password.
5. In Gmail settings, enable **IMAP** access (Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP).

Use your full Gmail address as `GMAIL_EMAIL` and the generated value as `GMAIL_APP_PASSWORD`.

## Telegram: bot + channel posting

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token into `TELEGRAM_BOT_TOKEN`.
2. Create a channel (or use an existing one).
3. Add the bot to the channel as a member, then promote it to **administrator** with permission to **post messages** (and send media/files as needed).
4. Set `TELEGRAM_CHAT_ID` to the channel username (for example `@my_channel`) or the channel’s numeric id (some setups require the numeric id).

**Tip:** You can forward a channel message to [@userinfobot](https://t.me/userinfobot) or similar tools to discover ids when needed.

## Configuration reference

| Variable | Required | Description |
| --- | --- | --- |
| `GMAIL_EMAIL` | yes | Gmail address used for IMAP login |
| `GMAIL_APP_PASSWORD` | yes | Gmail App Password (not your normal password) |
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | yes | `@channel` or numeric id |
| `GMAIL_IMAP_HOST` | no | Default `imap.gmail.com` |
| `GMAIL_IMAP_PORT` | no | Default `993` |
| `MAILBOX` | no | Default `INBOX` |
| `POLL_SECONDS` | no | Default `60` |
| `TZ` | no | IANA timezone for captions (example `Europe/Moscow`) |
| `STATE_PATH` | no | JSON state file path |
| `SEND_DOCUMENT` | no | If `true`, send non-images as documents; default **`false`** (images only) |
| `MAX_PHOTO_BYTES` | no | Max size for **`sendPhoto`** (default ~10 MiB) |
| `MAX_ATTACHMENT_BYTES` | no | Max size for **`sendDocument`** when `SEND_DOCUMENT=true` (~50 MiB default) |

Images are detected from MIME **`image/*`**, with a fallback for common image **file extensions**. Captions prefer the email **`Date`** header interpreted in `TZ`, plus subject; when the date header cannot be parsed, local time in `TZ` is used.

If **`SEND_DOCUMENT`** is **off** and a message has **only non-images** (or every image is over **`MAX_PHOTO_BYTES`**), nothing is posted and the message stays **UNSEEN** so it can be handled manually.

## Secrets and publishing to GitHub

- **Do not commit** `.env`, `state.json`, or any file that contains real tokens/passwords.
- **Do commit** code, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`, and this `README.md`.
- For CI/CD (for example GitHub Actions), store secrets in your platform’s **secret store** (GitHub **Actions secrets** / **Dependabot secrets** are separate) and inject them at deploy time—never bake them into the image or repository.
