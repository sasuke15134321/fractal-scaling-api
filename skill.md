# Fractal Scaling API — Skill

Progressive, reversible scaler for finite vector data. Pay-per-request via x402 USDC on Base.

## Purpose
Use Fractal Scaling API when you need to progressively select a deterministic subset of data points
from a 2D numeric dataset at a given scale fraction.

## When to use
- You have a 2D array of numeric data points and want a progressive, deterministic subset
- You need the selection to be reversible (returning to a prior scale gives identical results)
- You want coverage statistics over the selected subset
- You are building a progressive data loading or streaming system

## When not to use
- Transforming individual scalar values (this API selects indices, not transforms values)
- Image processing or signal filtering (not designed for that)
- Replacing a wallet or payment system

## Main endpoint (paid)

POST /scale — 0.02 USDC per successful request

### Example request
```json
{
  "points": [[0.0, 0.0], [1.0, 0.0], [0.5, 0.866], [0.5, 0.289]],
  "value": 0.5,
  "weights": null
}
```

### Example response
```json
{
  "selected_indices": [3, 0],
  "stats": {
    "scale": 0.5,
    "selected": 2,
    "total": 4,
    "reuse_from_previous": 1.0,
    "mean_coverage_distance": 0.577,
    "weighted_mean_coverage_distance": 0.577,
    "max_coverage_distance": 0.816
  }
}
```

## x402 payment flow
1. Call POST /scale without payment — receive HTTP 402 with x402 requirements
2. Pay 0.02 USDC on Base (eip155:8453) via a compatible x402 client
3. Retry POST /scale with X-PAYMENT or PAYMENT-SIGNATURE header containing the signed payment
4. Receive the scale result

## Key properties
- Deterministic: same points + value → same selected_indices
- Progressive: larger value → superset of smaller value result
- Reversible: same points + same value → always same indices
- stats() is observational: does not affect subsequent scale() calls
