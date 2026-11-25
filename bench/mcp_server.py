#!/usr/bin/env python3
"""Minimal MCP stdio server imitating an issue tracker and a metrics API.

Usage: mcp_server.py <data.json>. Standard library only; newline-delimited JSON-RPC 2.0.
The tracker is deliberately "N+1": search returns summaries, details need one call per issue.
"""
import json
import sys

PAGE = 5
TOOLS = [
    {
        "name": "search_issues",
        "description": "Search the issue tracker for one customer's issues. Returns summaries (id, title, status) "
                       f"in pages of {PAGE}; pass next_cursor back as cursor for the next page. "
                       "Use get_issue for priority and other details.",
        "inputSchema": {"type": "object", "required": ["customer_id"], "properties": {
            "customer_id": {"type": "string", "description": "Customer id, for example C001"},
            "status": {"type": "string", "enum": ["open", "closed"]},
            "cursor": {"type": "string"}}},
    },
    {
        "name": "get_issue",
        "description": "Get one issue with all fields: id, title, status, priority (P1 to P4), customer_id, created_at.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string", "description": "Issue id, for example ISS-1001"}}},
    },
    {
        "name": "get_service_metrics",
        "description": "Get Q1 2026 metrics for one service: requests, error_rate_pct, p50_ms.",
        "inputSchema": {"type": "object", "required": ["service"], "properties": {"service": {"type": "string"}}},
    },
]


def call(data, name, args):
    if name == "search_issues":
        rows = [i for i in data["issues"].values() if i["customer_id"] == args.get("customer_id")
                and args.get("status") in (None, i["status"])]
        start = int(args.get("cursor") or 0)
        page = rows[start:start + PAGE]
        return {"issues": [{"id": i["id"], "title": i["title"], "status": i["status"]} for i in page],
                "next_cursor": str(start + PAGE) if start + PAGE < len(rows) else None}
    if name == "get_issue":
        if args.get("id") not in data["issues"]:
            raise KeyError(f"no such issue: {args.get('id')}")
        return data["issues"][args["id"]]
    if name == "get_service_metrics":
        if args.get("service") not in data["metrics"]:
            raise KeyError(f"no such service: {args.get('service')}")
        return data["metrics"][args["service"]]
    raise KeyError(f"unknown tool: {name}")


def handle(data, msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                "serverInfo": {"name": "bench", "version": "1.0.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        try:
            payload = call(data, params.get("name"), params.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}
        except (KeyError, ValueError) as err:
            return {"content": [{"type": "text", "text": str(err)}], "isError": True}
    raise LookupError(method)


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:  # notification
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(data, msg)}
        except LookupError as err:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"method not found: {err}"}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
