import os
import sys
import time
import logging
import asyncio

from panoramisk import Manager, Message

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', filename='ami_poor.log')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import bitrix
import config
import ami_tools
import call_store

config_file = config.config_file
LOGGING = config.LOGGING


STATUSES = {
    "ABORT": 304,
    "ANSWER": 200,
    "BUSY": 486,
    "CANCEL": "603-S",
    "CHANUNAVAIL": 503,
    "CONGESTION": 403,
    "NOANSWER": 304
}


manager = Manager.from_config(config_file)

@manager.register_event('*')
async def ami_callback(mngr: Manager, message: Message):
    event = message.Event
    if LOGGING in [2,3] and event not in [
        'TestEvent',
        'PeerStatus',
        'Registry',
        'RTCPReceived',
        'RTCPSent'
    ]:
        logger.info(f"{event} {message}")

    if config.get_param('enabled', default="1") == "0":
        print("APP DISABLED", )
        return
    linked_id = message.Linkedid
    context = message.Context
    uniqueid = message.Uniqueid
    call_data = call_store.get_call_data(linked_id)

    if event == "Newchannel":
        if not call_data:
            caller = message.CallerIDnum
            exten = message.Exten
            insert_data = {
                'start_time': time.time(),
                'context': context,
                'uniqueid': uniqueid,
            }
            if config.get_context_type(context) == 'external':
                insert_data.update({"type": 2, "external": caller, "line_number": exten})
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
                                insert_data.update({"internal": internal})
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
                insert_data.update({"type": 1, "external": exten, "internal": caller, "pending": True})
            call_store.update_call_data(linked_id, **insert_data)
        else:
            call_store.update_call_data(linked_id, pending=False)
            internal_phone = message.Channel.split('/')[1].split('-')[0]
            if config.get_context_type(context) == 'internal':
                call_data['internal'] = internal_phone
                call_store.update_call_data(linked_id, internal=internal_phone)
            call_id = call_data.get('call_id')
            if not call_id:
                # ignore local calls
                if (config.get_context_type(context) == 'internal' and
                    config.get_context_type(call_data['context']) == 'internal'):
                    print("local call")
                    call_store.delete_call_data(linked_id)
                    return
                call_id = bitrix.register_call(call_data)
                call_store.update_call_data(linked_id, call_id=call_id)
            else:
                if config.get_param('show_card', default="1") == "1":
                    bitrix.card_action(call_id, internal_phone, 'show')
    elif not call_data:
        return

    elif event == "VarSet":
        if message.Variable == "MIXMONITOR_FILENAME":
            call_store.update_call_data(linked_id, file_path=message.Value)
        elif message.Variable == "VM_MESSAGEFILE" and config.get_bool_param('vm_send', default=True):
            call_store.update_call_data(linked_id, 
                                        file_path=f"{message.Value}.wav",
                                        is_voicemail=True)
    elif event == "Newexten":
        if message.Application == "VoiceMail":
            internal_phone = message.AppData.split('@')[0]
            call_store.update_call_data(linked_id, internal=internal_phone)
    elif event == "DialEnd":
        if message.DialStatus == "ANSWER" and call_data.get('type') == 2:
            internal_phone = message.DestChannel.split('/')[1].split('-')[0]
            call_store.update_call_data(linked_id, internal=internal_phone)
            if config.get_param('show_card', default="1") == "2":
                bitrix.card_action(call_data.get('call_id'), internal_phone, 'show')
        if call_data.get('status') != 200:
            dial_status = STATUSES.get(message.DialStatus)
            call_store.update_call_data(linked_id, status=dial_status)
    elif event == "Hangup":
        if call_data.get('uniqueid') == uniqueid:
            if call_data.get('pending'):
                call_store.delete_call_data(linked_id)
                return
            call_data['duration'] = round(time.time() - call_data['start_time'])
            resp = bitrix.finish_call(call_data)
            if resp and resp.status_code == 200:
                call_store.delete_call_data(linked_id)

def on_connect(mngr: Manager):
    print(
        'Connected to %s:%s AMI socket successfully' %
        (mngr.config['host'], mngr.config['port'])
    )

def run():
    print(f"AMI.sql started")
    manager.on_connect = on_connect
    manager.connect(run_forever=True)

if __name__ == '__main__':
    run()
