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


def update_db_user_context(peer, peer_type, context, context_map=None):
    if context and context_map is not None and context not in context_map:
        context_map[context] = peer
    
    conn = sqlite3.connect(APP_DB)
    cur = conn.execute("SELECT user_id FROM users WHERE user_phone=?", (peer,))
    row = cur.fetchone()
    if row and row[0]:
        conn.execute(
            "UPDATE users SET type=?, context=? WHERE user_id=?",
            (peer_type, context, row[0])
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO users(user_phone, type, context) VALUES (?, ?, ?)",
            (peer, peer_type, context)
        )
    conn.commit()
    conn.close()


async def get_sip_context(manager, peer):
    detail = await manager.send_action({'Action': 'SIPshowpeer', 'Peer': peer})
    return detail.get('Context')


async def get_pjsip_context(manager, endpoint):
    detail = await manager.send_action({'Action': 'PJSIPShowEndpoint', 'Endpoint': endpoint})
    if isinstance(detail, list):
        for d in detail:
            if d.get('Event') == 'EndpointDetail':
                return d.get('Context')
    return None


async def update_all_peers():
    manager = Manager.from_config(config_file)
    await manager.connect()
    context_map = {}
    # SIP peers
    sip_peers = await manager.send_action({'Action': 'SIPpeers'})
    if not sip_peers or not isinstance(sip_peers, list):
        if sip_peers and hasattr(sip_peers, 'get') and sip_peers.get('Response') == 'Error' and 'Invalid/unknown command' in sip_peers.get('Message', ''):
            print("SIPpeers command not found. Skipping SIP peers update.")
        else:
            print(sip_peers)
    else:
        for msg in sip_peers:
            if msg.get('Event') == 'PeerEntry' and msg.get('ObjectName'):
                peer = msg.get('ObjectName')
                context = await get_sip_context(manager, peer)
                update_db_user_context(peer, 'SIP', context, context_map)

    # PJSIP endpoints
    pjsip_endpoints = await manager.send_action({'Action': 'PJSIPShowEndpoints'})
    if isinstance(pjsip_endpoints, list):
        endpoints = [m for m in pjsip_endpoints if isinstance(m, dict) and m.get('Event') == 'EndpointList' and m.get('ObjectName')]
        for ep in endpoints:
            endpoint = ep.get('ObjectName')
            context = await get_pjsip_context(manager, endpoint)
            update_db_user_context(endpoint, 'PJSIP', context, context_map)
    elif isinstance(pjsip_endpoints, dict) and pjsip_endpoints.get('Response') == 'Error':
        pass  # Just ignore PJSIP errors or missing module to avoid crash
    
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


async def update_peer_context(peer):
    try:
        manager = Manager.from_config(config_file)
        await manager.connect()
        
        context = await get_sip_context(manager, peer)
        peer_type = 'SIP'
        
        if not context:
            context = await get_pjsip_context(manager, peer)
            peer_type = 'PJSIP'

        manager.close()

        if context:
            update_db_user_context(peer, peer_type, context)
    except Exception as e:
        print(f"Error updating context for {peer}: {e}")
