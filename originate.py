"""
https://github.com/gawel/panoramisk/blob/master/examples/originate.py

"""
from panoramisk.call_manager import CallManager
import logging
import redis
import time

r = redis.Redis(host='localhost', port=6379, db=1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='originate.log')
logger = logging.getLogger(__name__)

async def originate(internal, external, call_id):
    callmanager = CallManager.from_config('config.ini')
    await callmanager.connect()
    call = await callmanager.send_originate({
        'Action': 'Originate',
        'Channel': f'Local/{internal}@from-internal',
        'WaitTime': 20,
        'CallerID': external,
        'Exten': external,
        'Context': 'from-internal',
        'Account': call_id,
        'Priority': 1})
    while not call.queue.empty():
        event = call.queue.get_nowait()
        linked_id = event.Linkedid
        if event.Event == 'NewAccountCode' and event.AccountCode == call_id:
            call_data = r.json().get(linked_id, "$")
            if call_data is None:
                call_data = {
                    'start_time': time.time(),
                    'call_id': call_id,
                    'internal': internal,
                    'click2call': True
                }

                r.json().set(linked_id, "$", call_data)

    while True:
        event = await call.queue.get()
        # print(event)
        # logger.info(event)
        if event.event.lower() == 'hangup' and event.cause in ('0', '17'):
            break
    callmanager.clean_originate(call)
    callmanager.close()
