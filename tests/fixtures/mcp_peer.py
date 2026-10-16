"""Original stdio protocol peer for tests; contains no DAW/filesystem tools."""

import json
import sys
import time
from pathlib import Path

mode = sys.argv[1]
log = Path(sys.argv[2])
for line in sys.stdin:
    message = json.loads(line)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(message) + "\n")
    if "id" not in message:
        continue
    if mode == "hang":
        time.sleep(5)
        continue
    if mode == "eof":
        break
    if mode == "malformed":
        print("not JSON", flush=True)
        continue
    if mode == "wrong-id":
        print(json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}), flush=True)
        continue
    if mode == "error":
        print(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32603, "message": "authored error"},
                }
            ),
            flush=True,
        )
        continue
    if message["method"] == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {} if mode == "no-tools-exit" else {"tools": {}},
            "serverInfo": {"name": "authored-stdio-peer", "version": "1"},
        }
    elif message["method"] == "ping":
        result = {}
    else:
        result = {"tools": [{"name": "fixture_only", "inputSchema": {"type": "object"}}]}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
    if mode == "no-tools-exit" and message["method"] == "ping":
        break
