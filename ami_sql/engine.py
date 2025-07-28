import sqlite3
import time
import sys
import os
import logging
import time

from panoramisk import Manager, Message

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(message)s', filename='ami_poor.log')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import bitrix
import config
from config import get_param

config_file = config.config_file
LOGGING = config.LOGGING
APP_DB = config.APP_DB


STATUSES = {
    "ABORT": 304,
    "ANSWER": 200,
    "BUSY": 486,
    "CANCEL": "603-S",
    "CHANUNAVAIL": 503,
    "CONGESTION": 403,
    "NOANSWER": 304
}

conn = sqlite3.connect(APP_DB)

def get_call_data(linked_id):
    cur = conn.execute('SELECT * FROM calls WHERE linked_id = ?', (linked_id,))
    row = cur.fetchone()
    if row:
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))
    return None

def update_call_data(linked_id, **kwargs):
    call_data = get_call_data(linked_id)
    keys, vals = list(kwargs.keys()), list(kwargs.values())
    if call_data:
        set_clause = ', '.join(f'{k}=?' for k in keys)
        conn.execute(f'UPDATE calls SET {set_clause} WHERE linked_id=?', (*vals, linked_id))
    else:
        fields = ', '.join(['linked_id'] + keys)
        q = ', '.join(['?'] * (len(keys) + 1))
        conn.execute(f'INSERT INTO calls ({fields}) VALUES ({q})', (linked_id, *vals))
    conn.commit()

def delete_call_data(linked_id):
    conn.execute('DELETE FROM calls WHERE linked_id=?', (linked_id,))
    conn.commit()


manager = Manager.from_config(config_file)

@manager.register_event('*')
async def ami_callback(mngr: Manager, message: Message):
    if int(get_param('enabled')) != 1:
        print("APP DISABLED", )
        return
    event = message.Event
    if LOGGING and event not in [
        'TestEvent',
        'PeerStatus',
        'Registry'
    ]:
        logger.info(f"{event} {message}")

    linked_id = message.Linkedid
    context = message.Context
    uniqueid = message.Uniqueid
    call_data = get_call_data(linked_id)

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
                insert_data.update({"type": 2, "external": caller})
            elif config.get_context_type(context) == 'internal':
                insert_data.update({"type": 1, "external": exten, "internal": caller})
            update_call_data(linked_id, **insert_data)
        else:
            internal_phone = message.Channel.split('/')[1].split('-')[0]
            if config.get_context_type(context) == 'internal':
                update_call_data(linked_id, internal=internal_phone)
            call_id = call_data.get('call_id')
            if not call_id:
                # ignore local calls
                if (config.get_context_type(context) == 'internal' and
                    config.get_context_type(call_data['context']) == 'internal'):
                    print("local call")
                    delete_call_data(linked_id)
                    return
                call_id = bitrix.register_call(call_data)
                update_call_data(linked_id, call_id=call_id)
            else:
                if int(get_param('show_card', default=1)) == 1:
                    bitrix.card_action(call_id, internal_phone, 'show')
    elif not call_data:
        return

    elif event == "VarSet":
        if message.Variable == "MIXMONITOR_FILENAME":
            update_call_data(linked_id, file_path=message.Value)
    elif event == "DialEnd":
        if message.DialStatus == "ANSWER" and config.get_context_type(context) == 'external':
            internal_phone = message.DestChannel.split('/')[1].split('-')[0]
            update_call_data(linked_id, internal=internal_phone)
            if int(get_param('show_card', default=1)) == 2:
                bitrix.card_action(call_data.get('call_id'), internal_phone, 'show')
        status = call_data.get('status')
        if status != 200:
            dial_status = STATUSES.get(message.DialStatus)
            update_call_data(linked_id, status=dial_status)
    elif event == "Hangup":
        if call_data.get('uniqueid') == uniqueid:
            call_data['duration'] = round(time.time() - call_data['start_time'])
            resp = bitrix.finish_call(call_data)
            if resp.status_code == 200:
                delete_call_data(linked_id)

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
