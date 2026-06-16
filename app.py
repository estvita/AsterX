import sys
import asyncio
import importlib
import sqlite3
from datetime import datetime
from flask import Flask, request, redirect, render_template, render_template_string, session

import bitrix
import ami_tools
import config

engine_name = config.ENGINE

try:
    engine_module = importlib.import_module(engine_name)
except ImportError as e:
    sys.exit(f"Failed to import module '{engine_name}': {e}")

app = Flask(__name__)
app.secret_key = config.get_param('secret_key') or 'asterx-local'

LOGIN_TEMPLATE = '''
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>AsterX</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; color: #222; }
    main { max-width: 360px; margin: 80px auto; }
    label { display: block; margin: 12px 0 4px; font-weight: 600; }
    input { box-sizing: border-box; width: 100%; padding: 8px; }
    button { margin-top: 12px; padding: 9px 14px; cursor: pointer; }
    .error { color: #b00020; }
  </style>
</head>
<body>
<main>
  <h1>AsterX</h1>
  {% if error %}<p class="error">Invalid password</p>{% endif %}
  <form method="post" action="/login">
    <label>Password</label>
    <input type="password" name="password" autofocus>
    <button type="submit">Sign in</button>
  </form>
</main>
</body>
</html>
'''


def ui_password():
    return config.get_param('password')


def ui_allowed():
    password = ui_password()
    return not password or session.get('ui_authenticated') == '1'


def require_ui_auth():
    if ui_allowed():
        return None
    return redirect('/login')

def get_app_settings():
    keys = {
        'client_id': '',
        'client_secret': '',
        'default_user_id': '1',
        'show_card': '1',
        'crm_create': '1',
        'smart_route': '0',
        'vm_send': '1',
    }
    return {key: config.fetch_from_db(key) or default for key, default in keys.items()}


def get_contexts():
    config.prepare_db()
    conn = sqlite3.connect(config.APP_DB)
    rows = conn.execute(
        '''
        SELECT context, type FROM context
        UNION
        SELECT context, NULL FROM users WHERE context IS NOT NULL AND context != ''
        ORDER BY context
        '''
    ).fetchall()
    conn.close()
    result = []
    seen = set()
    for context_name, context_type in rows:
        if context_name in seen:
            continue
        seen.add(context_name)
        result.append({
            'context': context_name,
            'type': context_type or config.get_context_type(context_name) or 'excluded',
        })
    return result


def token_expires_text():
    expires = config.fetch_from_db('expires')
    if not expires:
        return 'unknown'
    try:
        return datetime.fromtimestamp(int(expires)).strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return expires


def render_settings():
    portal = config.fetch_from_db('domain') or config.fetch_from_db('client_endpoint')
    return render_template(
        'settings.html',
        portal=portal,
        member_id=config.fetch_from_db('member_id'),
        expires_text=token_expires_text(),
        settings=get_app_settings(),
        contexts=get_contexts(),
        password_enabled=bool(ui_password()),
    )


@app.route('/', methods=['GET'])
def project_info():
    auth_redirect = require_ui_auth()
    if auth_redirect:
        return auth_redirect
    return render_settings()


@app.route('/settings', methods=['POST'])
def save_settings():
    auth_redirect = require_ui_auth()
    if auth_redirect:
        return auth_redirect
    config.save_params({
        'client_id': request.form.get('client_id', ''),
        'client_secret': request.form.get('client_secret', ''),
        'default_user_id': request.form.get('default_user_id', '1'),
        'show_card': request.form.get('show_card', '1'),
        'crm_create': request.form.get('crm_create', '1'),
        'smart_route': request.form.get('smart_route', '0'),
        'vm_send': request.form.get('vm_send', '0'),
    })
    contexts = []
    for key, value in request.form.items():
        if key.startswith('context:'):
            contexts.append({key.split(':', 1)[1]: value})
    if contexts:
        config.update_contexts_table(contexts)
    return redirect('/')


@app.route('/refresh-token', methods=['POST'])
def refresh_token():
    auth_redirect = require_ui_auth()
    if auth_redirect:
        return auth_redirect
    bitrix.refresh_token()
    return redirect('/')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not ui_password():
        return redirect('/')
    if request.method == 'POST':
        if request.form.get('password') == ui_password():
            session['ui_authenticated'] = '1'
            return redirect('/')
        return render_template_string(LOGIN_TEMPLATE, error=True)
    return render_template_string(LOGIN_TEMPLATE, error=False)


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('ui_authenticated', None)
    return redirect('/login')
    

@app.route('/asterx', methods=['GET', 'POST'])
async def b24_handler():
    if request.method == 'GET':
        auth_redirect = require_ui_auth()
        if auth_redirect:
            return auth_redirect
        return render_settings()
    
    print(request.form)

    event = request.form.get('event')

    if event == 'ONAPPINSTALL':
        if bitrix.save_install_auth(request.form) is None:
            return 'Portal already installed', 403
        handler_url = config.get_param('handler_url') or request.url
        bitrix.bind_events(handler_url)
        return 'installed'

    application_token = request.form.get('auth[application_token]')
    saved_application_token = config.fetch_from_db('application_token')
    if not saved_application_token or application_token != saved_application_token:
        return 'Error', 403

    if event == 'ONEXTERNALCALLSTART':
        user_id = request.form.get('data[USER_ID]')
        call_id = request.form.get('data[CALL_ID]')
        external = request.form.get('data[PHONE_NUMBER]')
        endpoint = bitrix.get_user_phone(user_id)
        if endpoint:
            internal, context = endpoint
            await ami_tools.originate(internal, context, external, call_id)

        else:
            bitrix.finish_call({'call_id': call_id}, user_id)

    elif event == 'ONEXTERNALCALLBACKSTART':
        external = request.form.get('data[PHONE_NUMBER]')
        try:
            resp = bitrix.call_bitrix('telephony.externalCall.searchCrmEntities', {'PHONE_NUMBER': external})
            if resp:
                result = resp.json().get('result', [])
                assigned_by = result[0].get('ASSIGNED_BY', {})
                user_id = assigned_by.get('ID')
                endpoint = bitrix.get_user_phone(user_id)
                if endpoint:
                    internal, context = endpoint
                    payload = {
                        'external': external,
                        'type': 4
                    }
                    call_id = bitrix.register_call(payload, user_id)
                    await ami_tools.originate(internal, context, external, call_id)
        except Exception as e:
            print(event, f"Error: {e}")

    return 'event processed'
    

if __name__ == '__main__':
  
    app.run(debug=config.APP_DEBUG, host='0.0.0.0', port=config.APP_PORT, use_reloader=False)
