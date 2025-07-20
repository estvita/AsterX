import sys
import os
import logging
import time
import redis

from panoramisk import Manager, Message

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(message)s', filename='ami_poor.log')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import bitrix
import config

config_file = config.config_file
LOGGING = config.LOGGING
REDIS_DB = config.REDIS_DB
EXTERNAL_CONTEXTS = config.EXTERNAL_CONTEXTS
INTERNAL_CONTEXTS = config.INTERNAL_CONTEXTS
SHOW_CARD = int(config.SHOW_CARD)


STATUSES = {
    "ABORT": 304,
    "ANSWER": 200,
    "BUSY": 486,
    "CANCEL": "603-S",
    "CHANUNAVAIL": 503,
    "CONGESTION": 403,
    "NOANSWER": 304
}

r = redis.Redis(host='localhost', port=6379, db=REDIS_DB)
manager = Manager.from_config(config_file)

@manager.register_event('*')
async def ami_callback(mngr: Manager, message: Message):
    event = message.Event
    linked_id = message.Linkedid
    context = message.Context
    uniqueid = message.Uniqueid

    call_data = r.json().get(linked_id, "$")

    if event == "Newchannel":
        if not call_data:
            call_data = {
                'start_time': time.time(),
                'context': context,
                'uniqueid': uniqueid,
            }
            caller = message.CallerIDnum
            exten = message.Exten
            if context in EXTERNAL_CONTEXTS:
                call_data.update({"type": 2, "external": caller})
            elif context in INTERNAL_CONTEXTS:
                call_data.update({"type": 1, "external": exten, "internal": caller})
            r.json().set(linked_id, "$", call_data)
            r.expire(linked_id, 7200)
        else:
            internal_phone = message.Channel.split('/')[1].split('-')[0]
            if context in INTERNAL_CONTEXTS:
                r.json().set(linked_id, "$.internal", internal_phone)

            call_data = call_data[0]
            call_id = call_data.get('call_id')
            if not call_id:
                # ignore local calls
                if context in INTERNAL_CONTEXTS and call_data['context'] in INTERNAL_CONTEXTS:
                    print("local call")
                    r.json().delete(linked_id, "$")
                    return
                call_id = bitrix.register_call(call_data)
                r.json().set(linked_id, "$.call_id", call_id)
            else:
                if SHOW_CARD == 1:
                    bitrix.card_action(call_id, internal_phone, 'show')

    elif not call_data:
        return
    
    elif event == "VarSet":
        if message.Variable == "MIXMONITOR_FILENAME":
            r.json().set(linked_id, "$.file_path", message.Value)    

    elif event == "DialEnd":
        call_data = call_data[0]
        if message.DialStatus == "ANSWER":
            internal_phone = message.DestChannel.split('/')[1].split('-')[0]
            r.json().set(linked_id, "$.internal", internal_phone)
            if SHOW_CARD == 2:
                bitrix.card_action(call_data.get('call_id'), internal_phone, 'show')
        status = call_data.get('status')
        if status != 200:
            dial_status = STATUSES.get(message.DialStatus)
            r.json().set(linked_id, "$.status", dial_status)

    elif event == "Hangup":
        call_data = call_data[0]
        if call_data.get('uniqueid') == uniqueid:
            call_data['duration'] = round(time.time() - call_data['start_time'])
            bitrix.finish_call(call_data)
            r.json().delete(linked_id, "$")


def on_connect(mngr: Manager):
    print(
        'Connected to %s:%s AMI socket successfully' %
        (mngr.config['host'], mngr.config['port'])
    )

def run():
    print(f"AMI.poor started")
    manager.on_connect = on_connect
    manager.connect(run_forever=True)

if __name__ == '__main__':
    run()