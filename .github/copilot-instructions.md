# Bitrix-Asterisk Integration Copilot Instructions

## Project Overview
This project integrates Asterisk PBX with Bitrix24 CRM. It acts as a middleware that:
1. Receives webhooks from Bitrix24 (e.g., Click-to-Call) via a Flask web server.
2. Controls Asterisk via AMI (Asterisk Manager Interface) using `panoramisk`.
3. Syncs user data and logs calls back to Bitrix24.

## Architecture & Core Components

- **Web Server (`app.py`)**: Flask application handling Bitrix24 webhooks (`/asterx`). Uses `async` route handlers.
- **Asterisk Interface (`ami_tools.py`)**: Manages AMI connections using `panoramisk`. Handles actions like `Originate` and `SIPpeers`.
- **Bitrix Client (`bitrix.py`)**: Handles Bitrix24 REST API interactions (auth, token refresh, user sync, call logging).
- **Configuration (`config.py`)**: Parses `config.ini` and initializes the SQLite database (`APP_DB`).
- **Data Storage**: 
  - **SQLite**: Stores local cache of users (`users` table) and contexts (`context` table).
  - **Redis**: Optional backend (referenced in config).
- **Pluggable Engines**: The project supports different engines (e.g., `ami_sql`, `ami_redis`) loaded dynamically based on `config.ENGINE`.

## Key Patterns & Conventions

### Asyncio & Concurrency
- The project heavily relies on `asyncio`.
- Flask routes in `app.py` are `async`.
- AMI interactions in `ami_tools.py` are asynchronous.
- **Rule**: Always use `async/await` when interacting with Asterisk or defining web handlers.

### Database Access
- SQLite is used for local state.
- Connections are typically opened and closed per function call (e.g., in `bitrix.py`).
- **Schema**:
  - `users`: `user_phone`, `user_id` (Bitrix ID), `type`, `context`.
  - `context`: `context`, `type`.

### Bitrix Integration
- **Token Management**: `bitrix.py` handles token refreshing automatically.
- **Error Handling**: Bitrix API calls should handle `401` errors by attempting a token refresh.
- **Logging**: Extensive logging of Bitrix requests/responses is controlled by `config.LOGGING`.

### Configuration
- Settings are loaded from `config.ini`.
- Use `config.get_param()` or access `config` module variables directly.

## Developer Workflow

### Running the Application
- **Web Server**: `gunicorn -c gunicorn_config.py wsgi:app` (implied).
- **Standalone/Main**: `python main.py` (initializes DB and loads engine).

### Dependencies
- Managed in `requirements/full.txt`.
- Key libs: `panoramisk`, `flask[async]`, `requests`, `sqlite3`.

## Specific Coding Guidelines
1. **AMI Actions**: When adding new Asterisk commands, add them to `ami_tools.py` using the `manager.send_action` pattern.
2. **Bitrix Methods**: Use `bitrix.call_bitrix(method, payload)` wrapper for all CRM interactions to ensure auth handling.
3. **User Mapping**: Always resolve internal extensions to Bitrix User IDs using `bitrix.get_user_id` or `bitrix.get_user_phone` before logging calls.
