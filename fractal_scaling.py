"""Fractal Scaling v0.1 experimental primitive.

Scale discrete vector data progressively and reversibly. Optional external
weights bias which units appear earlier without assigning meaning to them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
import numpy as np


@dataclass(frozen=True)
class ScaleStats:
    scale: float
    selected: int
    total: int
    reuse_from_previous: float
    mean_coverage_distance: float
    weighted_mean_coverage_distance: float
    max_coverage_distance: float


class FractalScaler:
    """Progressive, reversible scaler for finite vector data.

    Public contract:
      - ``scale(value)`` accepts a finite value in [0, 1].
      - Increasing scale returns a superset prefix of the same deterministic
        progressive order; returning to a prior scale returns identical ids.
      - ``stats(value)`` is observational and does not mutate scaler state.
      - weights are optional, finite, non-negative external modifiers.

    v0.1 deliberately uses Euclidean distance over numeric vectors. It does not
    interpret the data or the semantic meaning of weights.
    """

    def __init__(
        self,
        points: np.ndarray,
        weights: Optional[Iterable[float]] = None,
        weight_floor: float = 0.15,
        beta: float = 1.0,
    ):
        x = np.asarray(points, dtype=float)
        if x.ndim != 2 or len(x) == 0:
            raise ValueError("points must be a non-empty 2D array [n, dimensions]")
        if x.shape[1] == 0 or np.any(~np.isfinite(x)):
            raise ValueError("points must have at least one finite dimension")

        self.points = x
        self.n = len(x)

        if weights is None:
            w = np.ones(self.n, dtype=float)
        else:
            w = np.asarray(list(weights), dtype=float)
            if w.shape != (self.n,):
                raise ValueError("weights must contain one value per data unit")
            if np.any(~np.isfinite(w)) or np.any(w < 0):
                raise ValueError("weights must be finite and non-negative")
            maximum = float(w.max())
            w = w / maximum if maximum > 0 else np.zeros_like(w)

        if not np.isfinite(weight_floor) or not 0 < weight_floor <= 1:
            raise ValueError("weight_floor must be finite and in (0, 1]")
        if not np.isfinite(beta) or beta < 0:
            raise ValueError("beta must be finite and non-negative")

        self.weights = w
        self.weight_floor = float(weight_floor)
        self.beta = float(beta)
        self.modifier = (self.weight_floor + (1.0 - self.weight_floor) * w) ** self.beta
        self.order = self._build_progressive_order()
        self._previous = np.empty(0, dtype=int)
        self._last_reuse = 1.0

    def _count_for_scale(self, value: float) -> int:
        if not np.isfinite(value) or value < 0 or value > 1:
            raise ValueError("scale must be between 0 and 1")
        k = int(np.floor(value * self.n + 1e-12))
        if value > 0 and k == 0:
            k = 1
        return k

    def _build_progressive_order(self) -> np.ndarray:
        # Deterministic seed: nearest unit to the centroid. Stable argmin/argmax
        # makes ties resolve by the lowest input index.
        centroid = self.points.mean(axis=0)
        first = int(np.argmin(np.sum((self.points - centroid) ** 2, axis=1)))
        order = np.empty(self.n, dtype=int)
        order[0] = first
        chosen = np.zeros(self.n, dtype=bool)
        chosen[first] = True
        min_d2 = np.sum((self.points - self.points[first]) ** 2, axis=1)
        min_d2[first] = 0.0

        for k in range(1, self.n):
            score = np.sqrt(min_d2) * self.modifier
            score[chosen] = -1.0
            nxt = int(np.argmax(score))
            order[k] = nxt
            chosen[nxt] = True
            d2 = np.sum((self.points - self.points[nxt]) ** 2, axis=1)
            min_d2 = np.minimum(min_d2, d2)
        return order

    def scale(self, value: float) -> np.ndarray:
        """Return selected input indices for ``value`` in [0, 1]."""
        k = self._count_for_scale(value)
        selected = self.order[:k].copy()
        if len(self._previous):
            reused = np.intersect1d(self._previous, selected, assume_unique=True).size
            self._last_reuse = reused / len(self._previous)
        else:
            self._last_reuse = 1.0
        self._previous = selected
        return selected

    def coverage(self, selected: np.ndarray) -> tuple[float, float, float]:
        """Return mean, externally weighted mean, and max nearest distance."""
        selected = np.asarray(selected, dtype=int)
        if selected.ndim != 1:
            raise ValueError("selected must be a 1D array of input indices")
        if len(selected) == 0:
            return float("inf"), float("inf"), float("inf")
        if np.any(selected < 0) or np.any(selected >= self.n):
            raise ValueError("selected contains an out-of-range input index")

        min_d2 = np.full(self.n, np.inf)
        for idx in selected:
            d2 = np.sum((self.points - self.points[idx]) ** 2, axis=1)
            min_d2 = np.minimum(min_d2, d2)
        distances = np.sqrt(min_d2)
        mean = float(distances.mean())
        weighted = (
            float(np.average(distances, weights=self.weights))
            if float(self.weights.sum()) > 0
            else mean
        )
        return mean, weighted, float(distances.max())

    def stats(self, value: float) -> ScaleStats:
        """Return statistics for a scale without changing scaler state."""
        k = self._count_for_scale(value)
        selected = self.order[:k]
        if len(self._previous):
            reused = np.intersect1d(self._previous, selected, assume_unique=True).size
            reuse = reused / len(self._previous)
        else:
            reuse = 1.0
        mean, weighted, maximum = self.coverage(selected)
        return ScaleStats(value, len(selected), self.n, reuse, mean, weighted, maximum)
