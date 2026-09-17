import asyncio
import time
from pprint import pprint

import config
from panoramisk import Manager


async def main():
    output_path = f"{int(time.time())}.txt"
    manager = Manager.from_config(config.config_file)
    await manager.connect()
    try:
        with open(output_path, "w", encoding="utf-8") as output_file:
            result = await manager.send_action({"Action": "PJSIPShowEndpoints"})

            if not isinstance(result, list):
                pprint(result, stream=output_file)
                return

            endpoints = [
                item.get("ObjectName")
                for item in result
                if hasattr(item, "get")
                and item.get("Event") == "EndpointList"
                and item.get("ObjectName")
            ]

            print(f"Found {len(endpoints)} endpoints", file=output_file)

            for endpoint in endpoints:
                print(f"\n=== {endpoint} ===", file=output_file)
                detail = await manager.send_action(
                    {"Action": "PJSIPShowEndpoint", "Endpoint": endpoint}
                )
                pprint(detail, stream=output_file)
    finally:
        manager.close()

    print(f"Saved output to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
