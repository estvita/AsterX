# AsterX

AsterX sends Asterisk call history and recordings to Bitrix24 through AMI.

## Modes

- Bitrix24 local app: install the app in Bitrix24, store OAuth tokens locally, and receive `ONEXTERNALCALLSTART` / `ONEXTERNALCALLBACKSTART` events.
- Incoming webhook only: set `[bitrix] url` when you only need to send call statistics to Bitrix24.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/local_sql.txt
cp examples/config.ini config.ini
```

Edit `config.ini`:

```ini
[app]
mode = local
handler_url = https://your-public-url/asterx
password =

[bitrix]
url =

[asterisk]
host = localhost
port = 5038
username = asterx
secret = secret
```

`handler_url` is required for Bitrix24 event subscription. `password` protects the web UI when set.

## Run

```bash
python main.py
python app.py
```

Open:

```text
http://localhost:8000/
```

The web UI shows the connected portal, token expiration, Bitrix24 app credentials, call settings, and Asterisk context types.

## Bitrix24

For local app mode, set the app handler URL to:

```text
https://your-public-url/asterx
```

On `ONAPPINSTALL`, AsterX stores portal tokens and subscribes to:

- `ONEXTERNALCALLSTART`
- `ONEXTERNALCALLBACKSTART`

For webhook-only mode, leave the portal uninstalled and set:

```ini
[bitrix]
url = https://example.bitrix24.com/rest/1/webhook/
```
