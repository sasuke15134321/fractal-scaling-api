# Fractal Scaling API v0.1

Progressive, reversible scaler for finite vector data. Pay-per-request via x402 USDC on Base.

## Endpoints

| Method | Path | Cost | Description |
|--------|------|------|-------------|
| POST | /scale | 0.02 USDC | Progressive fractal selection of input point indices |
| GET | /health | free | Health check |
| GET | /.well-known/x402.json | free | x402 endpoint discovery |
| GET | /ai-agent-policy.json | free | Agent policy |
| GET | /llms.txt | free | LLM-readable description |
| GET | /skill.md | free | Skill description |
| GET | /openapi.yaml | free | OpenAPI spec |

## Quick start (local, TEST_MODE)

```bash
cd fractal_scaling
pip install -r requirements.txt
TEST_MODE=true uvicorn main:app --reload
```

Test:
```bash
curl -X POST http://localhost:8000/scale \
  -H "Content-Type: application/json" \
  -d '{"points": [[0,0],[1,0],[0.5,0.866],[0.5,0.289]], "value": 0.5}'
```

## Payment flow

Without a valid X-PAYMENT header, the server returns HTTP 402 with x402 v2 requirements:
- Network: Base (eip155:8453)
- Asset: USDC (0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
- Amount: 20000 (0.02 USDC in micro-units)
- Recipient: 0x60c402878EfcEcAe5733A88075328Aa2320C39BE

## Core

Core file: `../fractal_scaling.py` (FractalScaler, ScaleStats)
Core is imported at runtime — do not modify it.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| WALLET_ADDRESS | 0x60c... | Payment recipient |
| PRICE_USDC | 0.02 | Price per request |
| CDP_API_KEY_ID | | CDP Facilitator key ID |
| CDP_API_KEY_SECRET | | CDP Facilitator key secret |
| FACILITATOR_PRIVATE_KEY | | Fallback on-chain facilitator key |
| TEST_MODE | false | Skip payment verification (dev only) |
| PORT | 8000 | Server port |
