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

## Local configuration parameters

Parameters are read from `config.ini`. Values saved through the web UI override values from the file.

### `[app]`

| Parameter | Default | Description |
| --- | --- | --- |
| `mode` | `cloud` | Use `local` for local Bitrix24 app installation. |
| `debug` | `0` | Enables debug mode for the web app. |
| `port` | `8000` | Port for the local web UI. |
| `engine` | `ami_sql` | Asterisk event handler module. |
| `app_db` | `app.db` | SQLite database file for settings, users, and contexts. |
| `redis_db` | `1` | Redis database number. |
| `logging` | `0` | Connector logging mode: `0` disabled, `1` Bitrix24/control server requests, `2` AMI events, `3` all listed logs. |
| `verify` | `True` | Enables SSL certificate verification for Bitrix24 HTTP requests. Set to `False` to disable verification. |
| `handler_url` | - | Public URL for Bitrix24 events, usually `https://your-public-url/asterx`. |
| `password` | - | Password for the local web UI. Empty value disables UI password protection. |
| `default_user_id` | `1` | Bitrix24 user used when an internal number cannot be matched. |
| `show_card` | `1` | Call card display mode: `0` disabled, `1` on call, `2` on answer. |
| `crm_create` | `1` | CRM entity creation mode: `0` disabled, `1` all calls, `2` incoming only, `3` outgoing only. |
| `smart_route` | `0` | Enables smart routing for incoming calls when set to `1`. |
| `vm_send` | `1` | Sends voicemail recordings to Bitrix24 when enabled. |
| `client_first` | `0` | Click-to-call order: `0` calls the operator first, `1` calls the client first. |
| `wait_time` | `20` | Originate wait time in seconds. |

In cloud mode, `client_first` and `wait_time` can also be updated by the `setup_complete` and `settings_update` WebSocket events. Omitted fields use their default values.

### `[bitrix]`

| Parameter | Default | Description |
| --- | --- | --- |
| `url` | - | Incoming webhook URL for webhook-only mode. In local app mode OAuth tokens are stored after app installation. |
| `token` | - | Optional static token for integrations that require it. |

### `[asterisk]`

| Parameter | Default | Description |
| --- | --- | --- |
| `host` | `localhost` | Asterisk AMI host. |
| `port` | `5038` | Asterisk AMI port. |
| `username` | - | Asterisk AMI user. |
| `secret` | - | Asterisk AMI password. |
| `pbx_id` | `0` | PBX identifier. Mostly used in cloud connector mode. |
| `records_protocol` | `local` | Recording access mode: `local`, `http`, `https`, or `sftp`. |
| `records_uri` | `0` | Base URI/path for call recordings when they are not read locally. |
| `record_user` | `0` | User for remote recording access. |
| `record_pass` | `0` | Password for remote recording access. |
| `key_filepath` | `0` | SSH private key path for `sftp` recording access. |
| `external_contexts` | `from-pstn` | Comma-separated Asterisk contexts treated as external. |
| `internal_contexts` | `from-internal` | Comma-separated Asterisk contexts treated as internal. |

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
