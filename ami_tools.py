import os
import sys
import time
import json
import asyncio
import sqlite3
from pprint import pprint
from panoramisk import Manager
from panoramisk.call_manager import CallManager


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
APP_DB = config.APP_DB
config_file = config.config_file
manager = Manager.from_config(config_file)


async def run_action(action_obj):
    manager = Manager.from_config(config_file)
    await manager.connect()
    result = await manager.send_action(action_obj)
    # pprint(result)
    manager.close()
    return result


async def update_all_peers():
    manager = Manager.from_config(config_file)
    await manager.connect()
    context_map = {}
    # SIP peers
    sip_peers = await manager.send_action({'Action': 'SIPpeers'})
    if not sip_peers or not isinstance(sip_peers, list):
        print(sip_peers)
    else:
        for msg in sip_peers:
            if msg.get('Event') == 'PeerEntry' and msg.get('ObjectName'):
                peer = msg.get('ObjectName')
                detail = await manager.send_action({'Action': 'SIPshowpeer', 'Peer': peer})
                context = detail.get('Context')
                if context and context not in context_map:
                    context_map[context] = peer
                conn = sqlite3.connect(APP_DB)
                cur = conn.execute("SELECT user_id FROM users WHERE user_phone=?", (peer,))
                row = cur.fetchone()
                if row and row[0]:
                    conn.execute(
                        "UPDATE users SET type=?, context=? WHERE user_id=?",
                        ('SIP', context, row[0])
                    )
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO users(user_phone, type, context) VALUES (?, ?, ?)",
                        (peer, 'SIP', context)
                    )
                conn.commit()
                conn.close()

    # PJSIP endpoints
    pjsip_endpoints = await manager.send_action({'Action': 'PJSIPShowEndpoints'})
    endpoints = [m for m in pjsip_endpoints if m.get('Event') == 'EndpointList' and m.get('ObjectName')]
    for ep in endpoints:
        endpoint = ep.get('ObjectName')
        detail = await manager.send_action({'Action': 'PJSIPShowEndpoint', 'Endpoint': endpoint})
        context = None
        for d in detail:
            if d.get('Event') == 'EndpointDetail':
                context = d.get('Context')
        if context and context not in context_map:
            context_map[context] = endpoint
        conn = sqlite3.connect(APP_DB)
        cur = conn.execute("SELECT user_id FROM users WHERE user_phone=?", (endpoint,))
        row = cur.fetchone()
        if row and row[0]:
            conn.execute(
                "UPDATE users SET type=?, context=? WHERE user_id=?",
                ('PJSIP', context, row[0])
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO users(user_phone, type, context) VALUES (?, ?, ?)",
                (endpoint, 'PJSIP', context)
            )
        conn.commit()
        conn.close()
    manager.close()
    
    return context_map


def save_call_data(data):
    conn = sqlite3.connect(APP_DB)
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT OR REPLACE INTO calls (
            linked_id, start_time, context, uniqueid, type,
            external, internal, call_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        data
    )
    conn.commit()
    conn.close()


async def originate(internal, context, external, call_id=None):
    callmanager = CallManager.from_config(config_file)
    await callmanager.connect()
    call = await callmanager.send_originate(
        {
            'Action': 'Originate',
            'Channel': f'Local/{internal}@{context}',
            'WaitTime': 20,
            'CallerID': external,
            'Exten': external,
        }
    )
    data_saved = False
    while not call.queue.empty():
        event = call.queue.get_nowait()
        linkedid = event.Linkedid
        uniqueid = event.Uniqueid
        if call_id and event.Event == 'Newchannel' and not data_saved:
            save_call_data((
                linkedid,
                time.time(),
                context,
                uniqueid,
                1,
                external,
                internal,
                call_id
            ))
            data_saved = True
    callmanager.clean_originate(call)
    callmanager.close()