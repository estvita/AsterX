import os
import sys
import time
import redis
import logging
import asyncio

from panoramisk import Manager, Message

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(message)s', filename='ami_poor.log')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import bitrix
import config
import ami_tools

config_file = config.config_file
LOGGING = config.LOGGING
REDIS_DB = config.REDIS_DB
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
    if LOGGING in [2,3] and event not in [
        'TestEvent', 'DeviceStateChange', 'VarSet', 'RTCPReceived',
        'RTCPSent'
        ]:
        logger.info(f"{event}: {message}")
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
            if config.get_context_type(context) == 'external':
                call_data.update({"type": 2, "external": caller})
                if config.get_param('smart_route', default="0") == "1":
                    try:
                        resp = bitrix.call_bitrix('telephony.externalCall.searchCrmEntities', {'PHONE_NUMBER': caller})
                        if resp:
                            result = resp.json().get('result', [])
                            assigned_by = result[0].get('ASSIGNED_BY', {})
                            user_id = assigned_by.get('ID')
                            endpoint = bitrix.get_user_phone(user_id=user_id)
                            if endpoint:
                                internal, context = endpoint
                                call_data.update({"internal": internal})
                                payload = {
                                    "Action": "Redirect",
                                    "Channel": message.Channel,
                                    "Context": context,
                                    "Exten": internal,
                                    "Priority": 1
                                }
                                asyncio.create_task(ami_tools.run_action(payload))
                    except Exception as e:
                        logger.info(f"Smart routing failed: {e}")
            elif config.get_context_type(context) == 'internal':
                call_data.update({"type": 1, "external": exten, "internal": caller})
            r.json().set(linked_id, "$", call_data)
            r.expire(linked_id, 7200)
        else:
            internal_phone = message.Channel.split('/')[1].split('-')[0]
            if config.get_context_type(context) == 'internal':
                r.json().set(linked_id, "$.internal", internal_phone)
                call_data['internal'] = internal_phone

            call_data = call_data[0]
            call_id = call_data.get('call_id')
            if not call_id:
                # ignore local calls
                if (config.get_context_type(context) == 'internal' and 
                    config.get_context_type(call_data['context']) == 'internal'):
                    print("local call")
                    r.json().delete(linked_id, "$")
                    return
                call_id = bitrix.register_call(call_data)
                r.json().set(linked_id, "$.call_id", call_id)
            else:
                if int(config.get_param('show_card', default="1")) == "1":
                    bitrix.card_action(call_id, internal_phone, 'show')

    elif not call_data:
        return
    
    elif event == "VarSet":
        if message.Variable == "MIXMONITOR_FILENAME":
            r.json().set(linked_id, "$.file_path", message.Value)
        if message.Variable == "VM_MESSAGEFILE" and config.get_param('vm_send', default="1") == "1":
            r.json().set(linked_id, "$.file_path", f"{message.Value}.wav")
            r.json().set(linked_id, "$.status", 'vm')
    elif event == "DialEnd":
        call_data = call_data[0]
        if message.DialStatus == "ANSWER":
            internal_phone = message.DestChannel.split('/')[1].split('-')[0]
            r.json().set(linked_id, "$.internal", internal_phone)
            if int(config.get_param('show_card', default="1")) == "2":
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
    print(f"AMI.redis started")
    manager.on_connect = on_connect
    manager.connect(run_forever=True)

if __name__ == '__main__':
    run()