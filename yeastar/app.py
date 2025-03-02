from flask import Flask, request, jsonify
import configparser
import base64
import threading
import time

import sys
import os

import redis
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bitrix import *
from project_data import project_data

from get_token import send_heartbeat


config = configparser.ConfigParser()
config.read('config.ini')
APP_DEBUG = config.get('app', 'debug')
APP_PORT = config.get('app', 'port')
TOKEN_B24 = config.get('bitrix', 'token')
DEFAULT_PHONE = config.get('bitrix', 'default_phone')
API_URL_YS = config.get('yeastar', 'api_url')
UPD_PERIOD = config.getint('yeastar', 'upd_period')


STATUSES = {
    'ANSWERED': 200,
    'ANSWER': 200,
    'NO ANSWER': 304,
    'BUSY': 486,
}

r = redis.Redis(host='localhost', port=6379, db=0)


app = Flask(__name__)

def update_heartbeat_periodically():
    while True:
        send_heartbeat()
        time.sleep(UPD_PERIOD)

@app.route('/', methods=['GET', 'POST'])
def project_info():
    return jsonify(project_data)


async def ys_api(data: dict, method: str):
    token = r.get('yeastar_token').decode('utf-8')
    resp = requests.post(f'{API_URL_YS}{method}?token={token}', json=data)
    return resp


@app.route('/yeastar', methods=['POST'])
async def ys_handler():
    event_data = request.json
    # print(event_data)
    action = event_data.get('action')
    callid = event_data.get('callid')
    
    if not callid:
        return jsonify({"error": "Missing 'callid'"}), 400

    call_data = None

    if action == 'RING':
        outbound = event_data.get('outbound')
        if outbound:
            call_data = {
                'internal': outbound.get('from'),
                'external': outbound.get('to'),
                'type': 1
            }

    elif action == 'ALERT':
        inbound = event_data.get('inbound')
        if inbound:
            # print(event_data)
            call_data = {
                'internal': DEFAULT_PHONE,
                'external': inbound.get('from'),
                'type': 2
            }


    if call_data:
        try:
            call_id = register_call(call_data)
            call_data['call_id'] = call_id
            r.json().set(callid, "$", call_data)
        except Exception as e:
            print(f"Error processing call: {str(e)}")
            return jsonify({"error": "Failed to process call"}), 500
        
    if action == 'ANSWER':
        inbound = event_data.get('inbound')
        call_data = r.json().get(callid, "$")
        if inbound and call_data:
            ext = event_data.get('ext', {})
            if ext:
                extid = ext.get('extid')
                r.json().set(callid, "$.internal", extid)

    elif action == 'NewCdr':
        call_data = r.json().get(callid, "$")
        if call_data:
            call_data = call_data[0]
            call_data['duration'] = event_data.get('callduraction')
            status = event_data.get('status')
            call_data['status'] = STATUSES.get(status, 304)
            if status == 'ANSWERED':
                call_data['recording'] = event_data.get('recording')

            resp = finish_call(call_data)
            if resp.status_code == 200:
                if call_data.get('recording'):
                    resp = await ys_api({'recording': call_data.get('recording')}, 'recording/get_random')
                    if resp.status_code == 200:
                        data = resp.json()
                        url_string = f'recording/download?recording={data.get("recording")}&random={data.get("random")}'
                        token = r.get('yeastar_token').decode('utf-8')
                        file_data = requests.get(f'{API_URL_YS}{url_string}&token={token}')
                        if file_data.status_code == 200:
                            file_content = file_data.content
                            file_base64 = base64.b64encode(file_content).decode('utf-8')
                            upload_file(call_data, file_base64)
                r.json().delete(callid, "$")        

    return jsonify({"status": "ok"}), 200

    
@app.route('/click2call', methods=['POST'])
async def b24_handler():
    application_token = request.form.get('auth[application_token]')
    if application_token != TOKEN_B24:
        return 'Error', 403
    
    event = request.form.get('event')

    if event == 'ONEXTERNALCALLSTART':
        user_id = request.form.get('data[USER_ID]')
        call_id = request.form.get('data[CALL_ID]')
        external = request.form.get('data[PHONE_NUMBER]')
        internal = get_user_phone(user_id)

        call_data = {
            'call_id': call_id,
        }
        if internal:
            payload = {
                'caller': internal,
                'callee': external
            }
            resp = await ys_api(payload, 'call/dial')
            resp = resp.json()

            if resp['status'] == 'Success': 
                callid = resp['callid']

                r.json().set(callid, "$", call_data)
                return 'ok'
            else:
                call_data.update({
                    'internal': internal,
                })
                finish_call(call_data)
            
        else:
            finish_call(call_data, user_id)
        return 'ok'
    
    else:
        return 'Not supported event', 400

if __name__ == '__main__':
    updater_thread = threading.Thread(target=update_heartbeat_periodically)
    updater_thread.daemon = True
    updater_thread.start()

    app.run(debug=APP_DEBUG, host='0.0.0.0', port=APP_PORT)
