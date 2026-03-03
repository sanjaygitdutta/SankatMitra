"""
SankatMitra – SageMaker Inference Handler for RNN Route Prediction
Called by the SageMaker endpoint when route_lambda invokes the model.
"""
from __future__ import annotations

import json
import os
from typing import Dict

import numpy as np

from train import encode_features, URGENCY_MAP


def model_fn(model_dir: str):
    """Load trained Keras model from SageMaker model directory."""
    try:
        import tensorflow as tf
        model_path = os.path.join(model_dir, "rnn_model.keras")
        return tf.keras.models.load_model(model_path)
    except Exception as e:
        print(f"Model load error: {e} – using heuristic fallback")
        return None


def input_fn(request_body: str, request_content_type: str = "application/json"):
    """Parse incoming inference request."""
    if request_content_type == "application/json":
        data = json.loads(request_body)
        instances = data.get("instances", [data])
        features = [encode_features(inst) for inst in instances]
        arr = np.array(features, dtype=np.float32)
        return arr[:, np.newaxis, :]  # (N, 1, 8) sequence format
    raise ValueError(f"Unsupported content type: {request_content_type}")


def predict_fn(input_data: np.ndarray, model):
    """Run RNN inference or heuristic fallback."""
    if model is not None:
        duration_pred, congestion_pred, confidence_pred = model.predict(input_data)
        return {
            "duration": duration_pred.flatten().tolist(),
            "congestion_factor": congestion_pred.flatten().tolist(),
            "confidence": confidence_pred.flatten().tolist(),
        }

    # Heuristic fallback (no model available)
    n = input_data.shape[0]
    return {
        "duration": [900.0] * n,          # 15 min default
        "congestion_factor": [1.2] * n,
        "confidence": [0.70] * n,
    }


def output_fn(prediction: Dict, accept: str = "application/json") -> str:
    """Serialize predictions to JSON."""
    predictions = []
    for i in range(len(prediction["duration"])):
        predictions.append({
            "estimated_duration_s": float(prediction["duration"][i]),
            "congestion_factor": float(prediction["congestion_factor"][i]) + 1.0,
            "confidence": float(prediction["confidence"][i]),
        })
    return json.dumps({"predictions": predictions})
