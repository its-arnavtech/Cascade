from __future__ import annotations

from typing import Any

from services.shared.anomaly.models import ModelResult
from services.shared.features.schema import FEATURE_KEYS

try:
    from sklearn.ensemble import IsolationForest
except Exception as exc:  # pragma: no cover - depends on optional dependency
    IsolationForest = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = ""


def status(min_windows: int = 20) -> dict[str, Any]:
    if IsolationForest is None:
        return {"available": False, "reason": f"scikit-learn unavailable: {IMPORT_ERROR}", "min_windows": min_windows}
    return {"available": True, "reason": "", "min_windows": min_windows}


def isolation_forest_detect(window: dict[str, Any], history: list[dict[str, Any]], min_windows: int = 20, contamination: str | float = "auto") -> ModelResult:
    if IsolationForest is None:
        return ModelResult("isolation_forest", "ml_baseline", False, 0.0, 0.0, f"unavailable: scikit-learn not installed ({IMPORT_ERROR})", {"available": False})
    training_rows = [row for row in history if row.get("window_id") != window.get("window_id")]
    if len(training_rows) < min_windows:
        return ModelResult("isolation_forest", "ml_baseline", False, 0.0, 0.0, f"insufficient_history: need {min_windows}, found {len(training_rows)}", {"available": True, "history_count": len(training_rows)})
    matrix = [_vector(row) for row in training_rows]
    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(matrix)
    raw_score = float(model.decision_function([_vector(window)])[0])
    prediction = int(model.predict([_vector(window)])[0])
    is_anomaly = prediction == -1
    risk = min(1.0, max(0.0, 0.5 - raw_score))
    explanation = f"Isolation Forest decision_function={raw_score:.4f}; lower scores are more anomalous and are mapped to local risk, not probability"
    return ModelResult("isolation_forest", "ml_baseline", is_anomaly, raw_score, risk if is_anomaly else 0.0, explanation, {"available": True, "history_count": len(training_rows), "decision_function": raw_score, "prediction": prediction})


def _vector(row: dict[str, Any]) -> list[float]:
    values = []
    for key in FEATURE_KEYS:
        try:
            values.append(float(row.get(key) or 0.0))
        except (TypeError, ValueError):
            values.append(0.0)
    return values

