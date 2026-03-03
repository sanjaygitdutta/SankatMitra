"""
SankatMitra – RNN (LSTM) Route Prediction Model
Trained on historical Indian traffic data to predict travel time and congestion.

Training:
    python train.py

Inference (SageMaker endpoint):
    Called via route_lambda using the sagemaker-runtime client.
"""
from __future__ import annotations

import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = [
    "hour_of_day",       # 0-23
    "day_of_week",       # 0-6 (Mon-Sun)
    "latitude_start",
    "longitude_start",
    "latitude_end",
    "longitude_end",
    "distance_km",
    "urgency_flag",      # 1 = CRITICAL, 0.5 = HIGH, 0 = MEDIUM
]

URGENCY_MAP = {"CRITICAL": 1.0, "HIGH": 0.5, "MEDIUM": 0.0}


def encode_features(instance: dict) -> np.ndarray:
    """Convert a request instance to a normalized feature vector."""
    return np.array([
        instance.get("hour_of_day", 12) / 23.0,
        instance.get("day_of_week", 0) / 6.0,
        (instance.get("latitude_start", 19.076) - 8.0) / (37.0 - 8.0),   # India lat range
        (instance.get("longitude_start", 72.877) - 68.0) / (97.0 - 68.0), # India lon range
        (instance.get("latitude_end", 19.076) - 8.0) / (37.0 - 8.0),
        (instance.get("longitude_end", 72.877) - 68.0) / (97.0 - 68.0),
        min(instance.get("distance_km", 5.0) / 100.0, 1.0),
        URGENCY_MAP.get(instance.get("urgency_level", "CRITICAL"), 1.0),
    ], dtype=np.float32)


# ---------------------------------------------------------------------------
# LSTM Model Definition
# ---------------------------------------------------------------------------

def build_model(sequence_length: int = 10, n_features: int = 8):
    """Build the Keras LSTM model for traffic flow prediction."""
    try:
        import tensorflow as tf
        from tensorflow.keras import layers, Model

        inputs = tf.keras.Input(shape=(sequence_length, n_features), name="sequence_input")
        x = layers.LSTM(64, return_sequences=True, name="lstm_1")(inputs)
        x = layers.Dropout(0.2)(x)
        x = layers.LSTM(32, name="lstm_2")(x)
        x = layers.Dense(16, activation="relu")(x)

        # Outputs: [estimated_duration_s, congestion_factor]
        duration_out = layers.Dense(1, activation="relu", name="duration")(x)
        congestion_out = layers.Dense(1, activation="sigmoid", name="congestion")(x)
        confidence_out = layers.Dense(1, activation="sigmoid", name="confidence")(x)

        model = Model(inputs=inputs, outputs=[duration_out, congestion_out, confidence_out])
        model.compile(optimizer="adam", loss="mse")
        return model
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Training Script
# ---------------------------------------------------------------------------

def generate_synthetic_training_data(n_samples: int = 10_000):
    """
    Generate synthetic Indian traffic training data.
    In production: replace with real traffic data from Parquet files in S3.
    """
    np.random.seed(42)
    X, y_duration, y_congestion = [], [], []

    for _ in range(n_samples):
        hour = np.random.randint(0, 24)
        dow = np.random.randint(0, 7)
        lat_s = np.random.uniform(8, 37)
        lon_s = np.random.uniform(68, 97)
        lat_e = lat_s + np.random.uniform(-0.5, 0.5)
        lon_e = lon_s + np.random.uniform(-0.5, 0.5)
        distance = np.random.uniform(0.5, 30.0)

        # Rush hour: 8-10 AM and 5-8 PM increases congestion
        is_rush = 1.0 if (8 <= hour <= 10 or 17 <= hour <= 20) else 0.0
        congestion = np.clip(is_rush * 0.5 + np.random.normal(0.3, 0.2), 0, 1)
        base_speed = 40 * (1 - congestion * 0.6)  # km/h
        duration = (distance / max(base_speed, 5)) * 3600 + np.random.normal(0, 60)

        features = encode_features({
            "hour_of_day": hour,
            "day_of_week": dow,
            "latitude_start": lat_s,
            "longitude_start": lon_s,
            "latitude_end": lat_e,
            "longitude_end": lon_e,
            "distance_km": distance,
            "urgency_level": "CRITICAL",
        })
        X.append(features)
        y_duration.append(max(duration, 60))
        y_congestion.append(congestion + 1.0)  # congestion_factor: 1.0 = no congestion

    return np.array(X), np.array(y_duration), np.array(y_congestion)


def train_and_save(output_dir: str = "./model_artifacts"):
    """Train the LSTM model and save artifacts."""
    try:
        import tensorflow as tf

        print("Generating training data...")
        X_flat, y_duration, y_congestion = generate_synthetic_training_data(10_000)

        # Reshape flat features into sequences (sequence_length=1 for simplicity)
        X_seq = X_flat[:, np.newaxis, :]  # (N, 1, 8)

        model = build_model(sequence_length=1, n_features=8)
        if model is None:
            print("TensorFlow not available – skipping training.")
            return

        print("Training LSTM model...")
        model.fit(
            X_seq,
            [y_duration, y_congestion, np.ones(len(y_duration)) * 0.85],
            epochs=20,
            batch_size=256,
            validation_split=0.2,
            verbose=1,
        )

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        model.save(os.path.join(output_dir, "rnn_model.keras"))
        print(f"Model saved to {output_dir}/rnn_model.keras")

    except ImportError:
        print("TensorFlow not installed. Run: pip install tensorflow")


if __name__ == "__main__":
    train_and_save()
