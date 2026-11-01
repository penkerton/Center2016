"""Модели прогнозирования и метрики качества.

Логистическая регрессия реализована на numpy (softmax + L2), чтобы не тянуть
тяжёлые зависимости. Классы: 0 — победа хозяев, 1 — ничья, 2 — победа гостей.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

OUTCOME_HOME = 0
OUTCOME_DRAW = 1
OUTCOME_AWAY = 2


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


class SoftmaxRegression:
    """Мультиномиальная логистическая регрессия с L2-регуляризацией."""

    def __init__(self, *, l2: float = 0.05, learning_rate: float = 0.08, epochs: int = 600, seed: int = 20261031) -> None:
        self.l2 = l2
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.seed = seed
        self.weights: np.ndarray | None = None
        self.bias: np.ndarray | None = None
        self.mean: np.ndarray | None = None
        self.scale: np.ndarray | None = None
        self.classes_: list[int] = []

    def _standardize(self, X: np.ndarray) -> np.ndarray:
        assert self.mean is not None and self.scale is not None
        return (X - self.mean) / self.scale

    def fit(self, X: list[list[float]], y: list[int]) -> "SoftmaxRegression":
        X_array = np.asarray(X, dtype=float)
        y_array = np.asarray(y, dtype=int)
        self.classes_ = sorted(set(y_array.tolist()))
        if X_array.size == 0:
            raise ValueError("Пустая обучающая выборка")
        self.mean = X_array.mean(axis=0)
        scale = X_array.std(axis=0)
        scale[scale < 1e-9] = 1.0
        self.scale = scale
        Xn = self._standardize(X_array)

        n_samples, n_features = Xn.shape
        n_classes = len(self.classes_)
        index = {cls: idx for idx, cls in enumerate(self.classes_)}
        Y = np.zeros((n_samples, n_classes))
        for row, label in enumerate(y_array):
            Y[row, index[label]] = 1.0

        rng = np.random.default_rng(self.seed)
        W = rng.normal(0.0, 0.01, size=(n_features, n_classes))
        b = np.zeros(n_classes)
        mW = np.zeros_like(W)
        vW = np.zeros_like(W)
        mb = np.zeros_like(b)
        vb = np.zeros_like(b)
        beta1, beta2, eps = 0.9, 0.999, 1e-8

        for epoch in range(1, self.epochs + 1):
            logits = Xn @ W + b
            probs = softmax(logits)
            error = (probs - Y) / n_samples
            grad_W = Xn.T @ error + self.l2 * W
            grad_b = error.sum(axis=0)

            mW = beta1 * mW + (1 - beta1) * grad_W
            vW = beta2 * vW + (1 - beta2) * (grad_W**2)
            mb = beta1 * mb + (1 - beta1) * grad_b
            vb = beta2 * vb + (1 - beta2) * (grad_b**2)
            mW_hat = mW / (1 - beta1**epoch)
            vW_hat = vW / (1 - beta2**epoch)
            mb_hat = mb / (1 - beta1**epoch)
            vb_hat = vb / (1 - beta2**epoch)
            W -= self.learning_rate * mW_hat / (np.sqrt(vW_hat) + eps)
            b -= self.learning_rate * mb_hat / (np.sqrt(vb_hat) + eps)

        self.weights = W
        self.bias = b
        return self

    def predict_proba(self, X: list[list[float]]) -> list[tuple[float, float, float]]:
        if self.weights is None or self.bias is None:
            raise RuntimeError("Модель не обучена")
        X_array = np.asarray(X, dtype=float)
        probs = softmax(self._standardize(X_array) @ self.weights + self.bias)
        index = {cls: idx for idx, cls in enumerate(self.classes_)}
        result: list[tuple[float, float, float]] = []
        for row in probs:
            triple = [0.0, 0.0, 0.0]
            for cls, idx in index.items():
                triple[cls] = float(row[idx])
            total = sum(triple) or 1.0
            result.append((triple[0] / total, triple[1] / total, triple[2] / total))
        return result


def normalize(probs: tuple[float, float, float]) -> tuple[float, float, float]:
    total = sum(probs)
    if total <= 0:
        return (1 / 3, 1 / 3, 1 / 3)
    return (probs[0] / total, probs[1] / total, probs[2] / total)


def blend(probs: tuple[float, float, float], prior: tuple[float, float, float], weight: float) -> tuple[float, float, float]:
    """Стягивание прогноза к базовым частотам — простая калибровка."""
    return normalize(
        (
            probs[0] * (1 - weight) + prior[0] * weight,
            probs[1] * (1 - weight) + prior[1] * weight,
            probs[2] * (1 - weight) + prior[2] * weight,
        )
    )


@dataclass
class Metrics:
    n: int
    accuracy: float
    brier: float
    log_loss: float
    mean_confidence: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "accuracy": round(self.accuracy, 4),
            "brier": round(self.brier, 4),
            "log_loss": round(self.log_loss, 4),
            "mean_confidence": round(self.mean_confidence, 4),
        }


def evaluate(probs: list[tuple[float, float, float]], outcomes: list[int]) -> Metrics:
    if not probs:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0)
    correct = 0
    brier = 0.0
    log_loss = 0.0
    confidence = 0.0
    for probabilities, outcome in zip(probs, outcomes):
        probabilities = normalize(probabilities)
        predicted = max(range(3), key=lambda index: probabilities[index])
        if predicted == outcome:
            correct += 1
        for index in range(3):
            target = 1.0 if index == outcome else 0.0
            brier += (probabilities[index] - target) ** 2
        true_probability = max(probabilities[outcome], 1e-12)
        log_loss -= math.log(true_probability)
        confidence += max(probabilities)
    n = len(probs)
    return Metrics(
        n=n,
        accuracy=correct / n,
        brier=brier / n,
        log_loss=log_loss / n,
        mean_confidence=confidence / n,
    )


def calibration_table(
    probs: list[tuple[float, float, float]],
    outcomes: list[int],
    bins: int = 10,
) -> list[dict[str, float]]:
    """Надёжность прогноза победы хозяев по бинам уверенности."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for probabilities, outcome in zip(probs, outcomes):
        probability = normalize(probabilities)[0]
        index = min(bins - 1, int(probability * bins))
        buckets[index].append((probability, 1 if outcome == OUTCOME_HOME else 0))
    table: list[dict[str, float]] = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        count = len(bucket)
        table.append(
            {
                "bin": index,
                "from": round(index / bins, 2),
                "to": round((index + 1) / bins, 2),
                "n": count,
                "predicted": round(sum(item[0] for item in bucket) / count, 4),
                "observed": round(sum(item[1] for item in bucket) / count, 4),
            }
        )
    return table


def bootstrap_accuracy(
    probs: list[tuple[float, float, float]],
    outcomes: list[int],
    *,
    rounds: int = 500,
    seed: int = 20261031,
) -> tuple[float, float]:
    """95%-й интервал точности (percentile bootstrap)."""
    if not probs:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    n = len(probs)
    predicted = [max(range(3), key=lambda index: normalize(probability)[index]) for probability in probs]
    values = []
    for _ in range(rounds):
        indices = rng.integers(0, n, size=n)
        correct = sum(1 for index in indices if predicted[index] == outcomes[index])
        values.append(correct / n)
    values.sort()
    return (values[int(0.025 * rounds)], values[int(0.975 * rounds) - 1])
