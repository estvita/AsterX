# main.py

import sys
import importlib
import threading
import asyncio
from panoramisk import Message
from pprint import pprint
import asterx
import config
import ami_tools

def extract_core_info(msg: Message):
    output = msg.Output
    result = {}
    keys = ["Version:", "System:", "Entity ID:", "PBX UUID:"]
    key_map = {
        "Version:": "version",
        "System:": "system",
        "Entity ID:": "entity_id",
        "PBX UUID:": "pbx_uuid",
    }
    for line in output:
        line = line.strip()
        for k in keys:
            if line.startswith(k):
                result[key_map[k]] = line.split(":", 1)[1].strip()
    return result


def async_core_info(core_info_container):
    resp = asyncio.run(ami_tools.run_action({"Action": "Command", "Command": "core show settings"}))
    contexts_dict = asyncio.run(ami_tools.update_all_peers())
    info = extract_core_info(resp)
    contexts = [{"context": c, "endpoint": e} for c, e in contexts_dict.items()]
    info["contexts"] = contexts
    core_info_container['core_info'] = info


def main():
    config.prepare_db()
    engine_name = config.ENGINE
    app_mode = config.APP_MODE
    try:
        engine_module = importlib.import_module(engine_name)
    except ImportError as e:
        sys.exit(f"Failed to import module '{engine_name}': {e}")

    core_info = None
    core_info_res = {}
    t = threading.Thread(target=async_core_info, args=(core_info_res,))
    t.start()
    t.join()  # Дождаться результата
    if app_mode == 'cloud':
        core_info = core_info_res.get('core_info')
        # запуск asterx
        t2 = threading.Thread(target=asterx.run, kwargs={'core_info': core_info})
        t2.start()
    engine_module.run()

if __name__ == '__main__':    
    main()