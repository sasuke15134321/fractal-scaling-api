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

from payment_verifier import PaymentVerifier
from fractal_scaling import FractalScaler, ScaleStats

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x60c402878EfcEcAe5733A88075328Aa2320C39BE")
PRICE_USDC = os.getenv("PRICE_USDC", "0.02")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

_NETWORK = "eip155:8453"
_USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

app = FastAPI(
    title="Fractal Scaling API",
    version="0.1.0",
    description=(
        "Progressive, reversible scaler for finite vector data. "
        "POST /scale returns deterministic progressive selection indices for a 2D point set "
        "at a given scale value in [0, 1]. Pay-per-request via x402 USDC on Base."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

payment_verifier = PaymentVerifier()


def _payment_required_body(method: str, url: str) -> dict:
    amount_units = str(round(float(PRICE_USDC) * 1_000_000))
    return {
        "x402Version": 2,
        "error": "Payment required",
        "resource": {
            "url": url,
            "method": method,
            "description": "Fractal scale operation — 0.02 USDC per successful request",
            "mimeType": "application/json",
        },
        "accepts": [{
            "scheme": "exact",
            "network": _NETWORK,
            "amount": amount_units,
            "asset": _USDC_ADDRESS,
            "payTo": WALLET_ADDRESS,
            "maxTimeoutSeconds": 300,
            "extra": {"name": "USD Coin", "version": "2"},
            "resource": {"method": method, "mimeType": "application/json"},
        }],
    }


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
    if not TEST_MODE:
        payment_header = (
            request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")
        )
        if not payment_header:
            body = _payment_required_body("POST", str(request.url))
            return JSONResponse(
                status_code=402,
                content=body,
                headers={"Payment-Required": base64.b64encode(json.dumps(body).encode()).decode()},
            )
        is_valid = await payment_verifier.verify_payment(payment_header, WALLET_ADDRESS, PRICE_USDC)
        if not is_valid:
            raise HTTPException(status_code=402, detail="Payment verification failed")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
