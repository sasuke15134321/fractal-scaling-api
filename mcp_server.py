#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fractal Scaling API — MCP Server
Exposes POST /scale as an MCP tool via stdio transport.
Requires: pip install mcp httpx python-dotenv
"""
import asyncio, json, os, sys
from pathlib import Path

try:
    import httpx
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
except ImportError:
    print("Install: pip install mcp httpx", file=sys.stderr)
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

BASE_URL = os.getenv("FRACTAL_SCALING_URL", "http://localhost:8000")
API_KEY  = os.getenv("X_PAYMENT", "")

server = Server("fractal-scaling-api")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="scale",
            description=(
                "Progressive fractal selection of input point indices. "
                "Paid: 0.02 USDC per successful request via x402. "
                "Returns deterministic progressive index subset and coverage stats."
            ),
            inputSchema={
                "type": "object",
                "required": ["points", "value"],
                "properties": {
                    "points": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "2D array of data points [[x,y,...], ...]",
                    },
                    "value": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Scale fraction in [0, 1]",
                    },
                    "weights": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Optional per-point weights (non-negative)",
                    },
                    "weight_floor": {"type": "number", "default": 0.15},
                    "beta": {"type": "number", "default": 1.0},
                    "x_payment": {
                        "type": "string",
                        "description": "x402 v2 payment header value (base64-encoded signed payment)",
                    },
                },
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != "scale":
        raise ValueError(f"Unknown tool: {name}")

    x_payment = arguments.pop("x_payment", API_KEY)
    headers = {"Content-Type": "application/json"}
    if x_payment:
        headers["X-PAYMENT"] = x_payment

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{BASE_URL}/scale", json=arguments, headers=headers)

    return [types.TextContent(type="text", text=json.dumps(resp.json(), ensure_ascii=False))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
