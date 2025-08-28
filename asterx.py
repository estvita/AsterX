import websockets
import asyncio
import json
from pprint import pprint

import config
import bitrix
import ami_tools 

PBX_ID = config.PBX_ID
APP_DB = config.APP_DB
CONTROL_SERVER = config.CONTROL_SERVER_WS


async def listen(core_info=None):
    url = f'{CONTROL_SERVER}/ws/asterx/?server_id={PBX_ID}'
    while True:
        try:
            async with websockets.connect(url) as websocket:              
                print(f"Connected to control server {CONTROL_SERVER}")
                if core_info:
                    await websocket.send(json.dumps(core_info))
                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    print(data)
                    event = data.get('event')
                    if event == 'setup_complete':
                        config.save_param("enabled", 1)
                        config.save_param("member_id", data.get('member_id', ''))
                        config.save_param("domain", data.get('domain', ''))
                        config.save_param("protocol", data.get('protocol', ''))
                        config.save_param("access_token", data.get('access_token', ''))
                        config.save_param("user_token", data.get('user_token', ''))
                        config.save_param("show_card", data.get('show_card', ''))
                        config.save_param("crm_create", data.get('crm_create', ''))
                        config.save_param("vm_send", data.get('vm_send', ''))
                        config.save_param("smart_route", data.get('smart_route', ''))
                        config.save_param("default_user_id", data.get('default_user_id', ''))
                        bitrix.get_user_phone()
                    elif event == 'settings_update':
                        config.save_param("show_card", data.get('show_card', ''))
                        config.save_param("crm_create", data.get('crm_create', ''))
                        config.save_param("vm_send", data.get('vm_send', ''))
                        config.save_param("smart_route", data.get('smart_route', ''))
                        config.save_param("default_user_id", data.get('default_user_id', ''))
                    elif event == 'refresh_users':
                        config.clear_table('users')                        
                        bitrix.get_user_phone()
                        asyncio.create_task(ami_tools.update_all_peers())
                    elif event == 'app_disabled':
                        config.save_param("enabled", 0)
                    elif event == 'contexts_updated':
                        contexts = data.get('contexts', [])
                        if contexts:
                            config.update_contexts_table(contexts)
                    elif event == 'ONEXTERNALCALLSTART':
                        user_id = data.get('b24_user_id')
                        enabled = config.get_param('enabled')
                        if not user_id or not enabled:
                            continue
                        endpoint = bitrix.get_user_phone(user_id=user_id)
                        if endpoint:
                            internal, context = endpoint
                            external = data.get('phone_number')
                            call_id = data.get('call_id')
                            asyncio.create_task(ami_tools.originate(internal, context, external, call_id))
                    elif event == 'ONEXTERNALCALLBACKSTART':
                        try:
                            external = data.get('phone_number')
                            resp = bitrix.call_bitrix('telephony.externalCall.searchCrmEntities', {'PHONE_NUMBER': external})
                            if resp:
                                result = resp.json().get('result', [])
                                assigned_by = result[0].get('ASSIGNED_BY', {})
                                user_id = assigned_by.get('ID')
                                endpoint = bitrix.get_user_phone(user_id=user_id)
                                if endpoint:
                                    internal, context = endpoint
                                    payload = {
                                        'external': external,
                                        'type': 4
                                    }
                                    call_id = bitrix.register_call(payload, user_id)
                                    asyncio.create_task(ami_tools.originate(internal, context, external, call_id))
                        except Exception as e:
                            print(event, f"Error: {e}")
        except websockets.ConnectionClosed:
            print("Connection closed. Reconnecting in 10 sec....")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Error: {e}. Reconnecting in 10 sec...")
            await asyncio.sleep(10)

def run(core_info=None):
    asyncio.run(listen(core_info))