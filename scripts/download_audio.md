# Download audio from Railway

Run these one at a time. Stop and inspect after each block — don't paste the whole file blindly.

## 0. Prerequisites (one-time)

```bash
# install Railway CLI if you don't have it
brew install railway

# (optional) upgrade if you see "New version available"
brew upgrade railway
```

## 1. Login & link project

```bash
# log in via browser
railway login

# from the repo root, link to the right project + environment + service
cd ~/arealclimber/brainwave
railway link
```

`railway link` is interactive — pick the brainwave project, the right environment (usually `production`), and the service.

Verify:

```bash
railway status
```

## 2. List audio files on the container

```bash
railway ssh "ls -la /tmp/brainwave_audio/"
```

Each file is named `<session_id>.wav`. Copy the session_id you want (filename minus `.wav`).

## 3. Download a single file

### Option A — via the public download endpoint (preferred)

```bash
# get your service's public domain
railway domain

# then in a regular terminal (replace both placeholders)
SESSION_ID="20260519_053705_8ad4fd3c"
DOMAIN="your-service.up.railway.app"

curl -fSL -o "${SESSION_ID}.wav" \
  "https://${DOMAIN}/api/v1/download-audio/${SESSION_ID}"
```

### Option B — via SSH + base64 (no public URL needed)

```bash
SESSION_ID="20260519_053705_8ad4fd3c"

railway ssh "base64 /tmp/brainwave_audio/${SESSION_ID}.wav" \
  | base64 -d > "${SESSION_ID}.wav"
```

## 4. Download every audio file in one go

### Option A — loop over the endpoint

```bash
DOMAIN="your-service.up.railway.app"
mkdir -p ./railway_audio_dump
cd ./railway_audio_dump

# pull the filename list off the container, strip .wav, curl each one
railway ssh "ls /tmp/brainwave_audio/" \
  | tr -d '\r' \
  | grep '\.wav$' \
  | sed 's/\.wav$//' \
  | while read -r sid; do
      echo "Downloading ${sid}..."
      curl -fSL -o "${sid}.wav" \
        "https://${DOMAIN}/api/v1/download-audio/${sid}"
    done

cd -
```

### Option B — loop over SSH+base64 (no public URL needed)

```bash
mkdir -p ./railway_audio_dump
cd ./railway_audio_dump

railway ssh "ls /tmp/brainwave_audio/" \
  | tr -d '\r' \
  | grep '\.wav$' \
  | while read -r fname; do
      echo "Downloading ${fname}..."
      railway ssh "base64 /tmp/brainwave_audio/${fname}" \
        | base64 -d > "${fname}"
    done

cd -
```

## 5. Verify

```bash
ls -la ./railway_audio_dump/
# play one to sanity-check (macOS)
afplay ./railway_audio_dump/<some-session-id>.wav
```

## Notes

- `/tmp/brainwave_audio/` lives on the container's ephemeral disk — files vanish on redeploy / restart. The periodic 24h cleanup has been removed, so the only thing that wipes files now is container lifecycle.
- The endpoint `/api/v1/download-audio/{session_id}` validates `session_id` against `^[\w]+$` — must match the filename stem.
- If `railway ssh` returns immediately without entering a shell, always pass the command as an argument (`railway ssh "<cmd>"`) instead of relying on interactive mode.
