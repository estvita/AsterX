import sys
import os

from flask import Flask, request, jsonify
import threading
import configparser
from ari import engine
from ari import originate

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from bitrix import *
from project_data import project_data

config = configparser.ConfigParser()
config.read('config.ini')
APP_DEBUG = config.get('app', 'debug')
APP_PORT = config.get('app', 'port')
TOKEN = config.get('bitrix', 'token')

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def project_info():
    return jsonify(project_data)

@app.route('/click2call', methods=['POST'])
async def b24_handler():
    application_token = request.form.get('auth[application_token]')
    if application_token != TOKEN:
        return 'Error', 403
    
    event = request.form.get('event')

    if event == 'ONEXTERNALCALLSTART':
        user_id = request.form.get('data[USER_ID]')
        call_id = request.form.get('data[CALL_ID]')
        external = request.form.get('data[PHONE_NUMBER]')
        internal = get_user_phone(user_id)
        if internal:
            originate.originate(internal, external, call_id)

        else:
            finish_call({'call_id': call_id}, user_id)

        return 'ok'
    
    else:
        return 'Not supported event', 400

def run_engine():
    engine.run()

if __name__ == '__main__':
    # Запуск WebSocket клиента в отдельном потоке
    ari_thread = threading.Thread(target=run_engine, daemon=True)
    ari_thread.start()

    # Запуск Flask сервера
    app.run(debug=APP_DEBUG, host='0.0.0.0', port=APP_PORT, use_reloader=False)