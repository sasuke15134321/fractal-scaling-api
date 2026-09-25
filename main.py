#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fractal Scaling API v0.1
Progressive, reversible scaler for finite vector data. Pay-per-request via x402.
"""
import os, sys, json, base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import numpy as np
from contextlib import asynccontextmanager

from payment_verifier import _generate_cdp_jwt
from fractal_scaling import FractalScaler, ScaleStats

from x402 import x402ResourceServer
from x402.http.middleware.fastapi import payment_middleware
from x402.http.types import RouteConfig, PaymentOption
from x402.http.facilitator_client import HTTPFacilitatorClient
from x402.http.facilitator_client_base import FacilitatorConfig, CreateHeadersAuthProvider
from x402.mechanisms.evm.exact.register import register_exact_evm_server
from x402.extensions.bazaar import declare_discovery_extension, OutputConfig

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x60c402878EfcEcAe5733A88075328Aa2320C39BE")
PRICE_USDC = os.getenv("PRICE_USDC", "0.02")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

_NETWORK = "eip155:8453"
_USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

_CDP_BASE_URL = "https://api.cdp.coinbase.com/platform/v2/x402"


def _create_cdp_headers():
    return {
        "supported": {
            "Authorization": "Bearer " + _generate_cdp_jwt(
                "GET", "/platform/v2/x402/supported"
            )
        },
        "verify": {
            "Authorization": "Bearer " + _generate_cdp_jwt(
                "POST", "/platform/v2/x402/verify"
            )
        },
        "settle": {
            "Authorization": "Bearer " + _generate_cdp_jwt(
                "POST", "/platform/v2/x402/settle"
            )
        },
    }


_cdp_auth = CreateHeadersAuthProvider(_create_cdp_headers)

_facilitator = HTTPFacilitatorClient(
    FacilitatorConfig(
        url=_CDP_BASE_URL,
        auth_provider=_cdp_auth,
    )
)

_x402_server = x402ResourceServer(_facilitator)
register_exact_evm_server(_x402_server, _NETWORK)

_bazaar_extension = declare_discovery_extension(
    input={
        "points": [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.5, 0.866],
            [0.5, 0.289],
        ],
        "value": 0.5,
    },
    body_type="json",
    output=OutputConfig(
        example={
            "selected_indices": [3, 0],
            "stats": {
                "scale": 0.5,
                "selected": 2,
                "total": 4,
                "reuse_from_previous": 1.0,
                "mean_coverage_distance": 0.289,
                "weighted_mean_coverage_distance": 0.289,
                "max_coverage_distance": 0.578,
            },
        },
        schema={
            "type": "object",
            "properties": {
                "selected_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "stats": {"type": "object"},
            },
        },
    ),
)

_x402_routes = {
    "POST /scale": RouteConfig(
        accepts=PaymentOption(
            scheme="exact",
            pay_to=WALLET_ADDRESS,
            price="$" + PRICE_USDC,
            network=_NETWORK,
            max_timeout_seconds=300,
        ),
        description="Fractal scale operation - 0.02 USDC per successful request",
        mime_type="application/json",
        extensions=_bazaar_extension,
    )
}

_mcp_server = None  # populated at bottom of file; lifespan sees final value at startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _mcp_server is not None:
        async with _mcp_server.session_manager.run():
            yield
    else:
        yield


app = FastAPI(
    title="Fractal Scaling API",
    version="0.1.0",
    description=(
        "Progressive, reversible scaler for finite vector data. "
        "POST /scale returns deterministic progressive selection indices for a 2D point set "
        "at a given scale value in [0, 1]. Pay-per-request via x402 USDC on Base."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if TEST_MODE:
        return await call_next(request)
    return await payment_middleware(
        _x402_routes,
        _x402_server,
    )(request, call_next)



class ScaleRequest(BaseModel):
    points: List[List[float]] = Field(
        ...,
        description="2D array of data points [n, dimensions]. Non-empty, all finite.",
    )
    value: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Scale value in [0, 1]. 0 selects 0 points, 1 selects all n points.",
    )
    weights: Optional[List[float]] = Field(
        default=None,
        description="Optional per-point weights (non-negative, length must equal n).",
    )
    weight_floor: float = Field(default=0.15, gt=0.0, le=1.0)
    beta: float = Field(default=1.0, ge=0.0)


class ScaleResponse(BaseModel):
    selected_indices: List[int]
    stats: dict


@app.post(
    "/scale",
    response_model=ScaleResponse,
    summary="Scale — Progressive fractal selection (paid: 0.02 USDC)",
    description=(
        "Returns deterministic progressive selection of input point indices for the given scale value. "
        "Increasing scale always returns a superset of the previous result. "
        "Charged per successful request at 0.02 USDC via x402."
    ),
    responses={402: {"description": "Payment Required — include X-PAYMENT or PAYMENT-SIGNATURE header"}},
    tags=["Core"],
)
async def scale(payload: ScaleRequest, request: Request):

    try:
        pts = np.array(payload.points, dtype=float)
        scaler = FractalScaler(
            points=pts,
            weights=payload.weights,
            weight_floor=payload.weight_floor,
            beta=payload.beta,
        )
        selected = scaler.scale(payload.value)
        st = scaler.stats(payload.value)
        return {
            "selected_indices": selected.tolist(),
            "stats": {
                "scale": st.scale,
                "selected": st.selected,
                "total": st.total,
                "reuse_from_previous": st.reuse_from_previous,
                "mean_coverage_distance": st.mean_coverage_distance,
                "weighted_mean_coverage_distance": st.weighted_mean_coverage_distance,
                "max_coverage_distance": st.max_coverage_distance,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", include_in_schema=False)
async def health():
    return {
        "status": "healthy",
        "test_mode": TEST_MODE,
        "version": "0.1.0",
        "wallet_configured": bool(os.getenv("WALLET_ADDRESS")),
        "cdp_configured": bool(os.getenv("CDP_API_KEY_ID") and os.getenv("CDP_API_KEY_SECRET")),
    }


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Fractal Scaling API",
        "version": "0.1.0",
        "description": "Progressive, reversible scaler for finite vector data",
        "endpoints": {
            "scale": "POST /scale (paid: 0.02 USDC per request)",
            "health": "GET /health (free)",
            "discovery": "GET /.well-known/x402.json (free)",
        },
        "network": "base-mainnet",
        "currency": "USDC",
    }


@app.get("/.well-known/x402.json", include_in_schema=False)
async def x402_discovery():
    return {
        "version": 1,
        "endpoints": [{
            "path": "/scale",
            "method": "POST",
            "price": PRICE_USDC,
            "currency": "USDC",
            "network": "base",
            "description": "Progressive, reversible fractal scaling for finite vector data",
            "category": "data",
            "tags": ["scaling", "vector", "fractal", "selection", "ai"],
        }],
    }


@app.get("/.well-known/ai-agent-policy", include_in_schema=False)
async def ai_agent_policy():
    with open(Path(__file__).parent / "ai-agent-policy.json") as f:
        return json.load(f)


@app.get("/ai-agent-policy.json", include_in_schema=False)
async def ai_agent_policy_json():
    with open(Path(__file__).parent / "ai-agent-policy.json") as f:
        return json.load(f)


@app.get("/llms.txt", include_in_schema=False)
async def llms_txt():
    return PlainTextResponse(open(Path(__file__).parent / "llms.txt").read())


@app.get("/skill.md", include_in_schema=False)
async def skill_md():
    return PlainTextResponse(open(Path(__file__).parent / "skill.md").read())


@app.get("/openapi.yaml", include_in_schema=False)
async def openapi_yaml_endpoint():
    return PlainTextResponse(
        open(Path(__file__).parent / "openapi.yaml").read(), media_type="text/yaml"
    )


@app.get("/.well-known/mcp/server-card.json", include_in_schema=False)
async def mcp_server_card():
    return {
        "serverInfo": {"name": "fractal-scaling-api", "version": "0.1.0"},
        "tools": [
            {
                "name": "scale",
                "description": "Progressive fractal selection of input point indices (0.02 USDC). Returns deterministic progressive index subset and coverage stats.",
                "inputSchema": {
                    "type": "object",
                    "required": ["points", "value"],
                    "properties": {
                        "points": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "number"}},
                            "description": "2D array of data points [[x, y, ...], ...]",
                        },
                        "value": {"type": "number", "description": "Scale fraction in [0, 1]"},
                        "weights": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Optional per-point weights (non-negative)",
                        },
                        "weight_floor": {"type": "number", "default": 0.15},
                        "beta": {"type": "number", "default": 1.0},
                    },
                },
            }
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))


# ── MCP Server mount (Smithery registration at /mcp) ──────────────────────────
from mcp_server import mcp as _mcp_server  # noqa: E402

try:
    app.mount("/mcp", _mcp_server.streamable_http_app())
except Exception as _mcp_err:
    import logging
    logging.getLogger(__name__).warning(f"MCP mount failed: {_mcp_err}")
