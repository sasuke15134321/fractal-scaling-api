#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fractal Scaling API — MCP Server
stdio / Streamable HTTP dual transport via FastMCP.
"""
import os, json
from typing import List, Optional
import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.getenv("FRACTAL_SCALING_URL", "https://fractal-scaling-api.onrender.com").rstrip("/")
PAYMENT_TOKEN = os.getenv("MCP_PAYMENT_TOKEN", "")

mcp = FastMCP("Fractal Scaling API")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if PAYMENT_TOKEN:
        h["PAYMENT-SIGNATURE"] = PAYMENT_TOKEN
    return h


@mcp.tool()
async def scale(
    points: List[List[float]],
    value: float,
    weights: Optional[List[float]] = None,
    weight_floor: float = 0.15,
    beta: float = 1.0,
) -> str:
    """
    Progressive fractal selection of input point indices (0.02 USDC).
    Returns deterministic progressive index subset and coverage stats.
    Increasing scale always returns a superset of the previous result.

    Args:
        points:       2D array of data points [[x, y, ...], ...]
        value:        Scale fraction in [0, 1]
        weights:      Optional per-point weights (non-negative)
        weight_floor: Weight floor (default 0.15)
        beta:         Beta parameter (default 1.0)
    """
    payload: dict = {"points": points, "value": value, "weight_floor": weight_floor, "beta": beta}
    if weights is not None:
        payload["weights"] = weights

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{BASE_URL}/scale", json=payload, headers=_headers())
        if resp.status_code == 402:
            return json.dumps({"error": "Payment Required (x402)", "x402": resp.json()}, ensure_ascii=False)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
