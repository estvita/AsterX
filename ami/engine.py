import sys
import os
import time
import re
import json
import configparser
import logging
import requests
import base64

import redis

from panoramisk import Manager, Message

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import bitrix
import utils

config_file = 'config.ini'

config = configparser.ConfigParser()
config.read(config_file)

LOC_CONTEXTS = config.get('asterisk', 'loc_contexts')
IN_CONTEXTS = config.get('asterisk', 'in_contexts')
DEFAULT_PHONE = config.get('bitrix', 'default_phone')
LOCAL_COUNT = config.getint('asterisk', 'loc_count')
LOGGING = config.getboolean('asterisk', 'logging')
SHOW_CARD = config.getint('bitrix', 'show_card')
RECORD_PROTOCOL = config.get('asterisk', 'records_protocol')
RECORD_URI = config.get('asterisk', 'records_uri')
RECORD_USER = config.get('asterisk', 'record_user')
RECORD_PASS = config.get('asterisk', 'record_pass')

CONTEXTS = IN_CONTEXTS + LOC_CONTEXTS

STATUSES = {
    '3': 503,
    '17': 486,
    '19': 480,
    '20': 480,
    '21': 403,
    '31': 200,
    '34': 404,
    '38': 503,
    '127': 603,
}

r = redis.Redis(host='localhost', port=6379, db=1)

logging.basicConfig(level=logging.INFO, format='%(message)s', filename='log.txt')
logger = logging.getLogger()


manager = Manager.from_config(config_file)

@manager.register_event('*')
async def ami_callback(mngr: Manager, message: Message):
    linked_id = message.Linkedid
    # print(message)
    if LOGGING:
        logger = utils.setup_logger(linked_id)
        logger.info(message)


# add voicemail to call_data
@manager.register_event('VarSet')
async def ami_callback(mngr: Manager, message: Message):
    linked_id = message.Linkedid
    variable = message.Variable
    if variable == "VM_MESSAGEFILE":
        r.json().set(linked_id, "$.file_path", f"{message.Value}.wav")


@manager.register_event('CEL')
async def ami_callback(mngr: Manager, message: Message):
    linked_id = message.Linkedid
    context = message.Context
    event = message.EventName
    app = message.Application

    call_data = r.json().get(linked_id, "$")

    if event == 'CHAN_START':
        if call_data is None:
            call_data = {
                'start_time': time.time()
            }

            caller = message.CallerIDnum
            exten = message.Exten

            if exten == "s" or "*" in exten:
                return

            # Outbound call
            if context in LOC_CONTEXTS and len(exten) > LOCAL_COUNT:
                call_data.update({
                    'internal': caller,
                    'external': exten,
                    'type': 1
                })
            # Inbound call
            elif context in IN_CONTEXTS:
                call_data.update({
                    'internal': DEFAULT_PHONE,
                    'external': caller,
                    'type': 2
                })
            # Other contexts
            else:
                return
            
            call_data['call_id'] = bitrix.register_call(call_data)
            r.json().set(linked_id, "$", call_data)
            r.expire(linked_id, 7200)

    elif event == 'APP_START':
        if call_data:
            if app == 'MixMonitor':
                r.json().set(linked_id, "$.file_path", message.AppData.split(',')[0])
            elif app == 'Dial' and SHOW_CARD == 1:
                phone = re.split('[-@]', message.Channel.split('/')[1])[0]
                bitrix.card_action(call_data[0]['call_id'], phone, 'show')

    elif event == 'APP_END':
        if call_data:
            if app == 'Dial' and SHOW_CARD == 1:
                phone = re.split('[-@]', message.Channel.split('/')[1])[0]
                bitrix.card_action(call_data[0]['call_id'], phone, 'hide')

    elif event == 'PICKUP':
        if call_data:
            extra = json.loads(message.Extra)
            channel = extra.get('pickup_channel')
            r.json().set(linked_id, "$.internal", channel.split('/')[1].split('-')[0])
            r.json().set(linked_id, "$.status", 200)

    elif event == 'ANSWER':
        if call_data:
            if context in CONTEXTS:
                r.json().set(linked_id, "$.status", 200)
                if call_data[0]['type'] == 2:
                    r.json().set(linked_id, "$.internal", message.CallerIDnum)

    elif event == 'BLINDTRANSFER':
        if call_data:
            extra = json.loads(message.Extra)
            r.json().set(linked_id, "$.internal", extra.get('extension'))

    elif event == 'ATTENDEDTRANSFER':
        if call_data:
            extra = json.loads(message.Extra)
            target_internal = extra.get('transfer_target_channel_name')
            r.json().set(linked_id, "$.internal", target_internal.split('/')[1].split('@')[0])

    elif event == 'HANGUP':
        if call_data and context in LOC_CONTEXTS:
            status = call_data[0].get('status')
            extra = json.loads(message.Extra)
            status_code = STATUSES.get(str(extra.get('hangupcause')), 304)
            if status != 200 and 'click2call' not in call_data[0]:
                r.json().set(linked_id, "$.status", status_code)
                if call_data[0]['type'] == 2:
                    r.json().set(linked_id, "$.internal", message.CallerIDnum)
            elif status == 200 and 'click2call' in call_data[0]:
                if extra.get('dialstatus') in ['CANCEL', 'BUSY', 'NOANSWER']:
                    r.json().set(linked_id, "$.status", status_code)

    elif event == 'LINKEDID_END':
        if call_data:
            call_data = call_data[0]
            call_data['duration'] = round(time.time() - call_data['start_time'])
            resp = bitrix.finish_call(call_data)
            if resp.status_code == 200 and call_data.get('status') == 200:
                if call_data.get('file_path') and RECORD_URI:
                    file_path = call_data.get('file_path')
                    file_path = f'{RECORD_URI}{file_path}'
                    if RECORD_PROTOCOL == "sftp":
                        file_content = utils.download_file_sftp(file_path)
                    else:
                        file_data = requests.get(file_path, auth=(RECORD_USER, RECORD_PASS))
                        if file_data.status_code == 200:
                            file_content = file_data.content

                    if file_content:
                        file_base64 = base64.b64encode(file_content).decode('utf-8')
                        bitrix.upload_file(call_data, file_base64)
            r.json().delete(linked_id, "$")


def run():
    print(f"AMI engine started")
    manager.connect(run_forever=True)

if __name__ == '__main__':
    run()