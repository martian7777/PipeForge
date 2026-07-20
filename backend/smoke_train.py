"""Milestone 3 smoke test: async training run -> leaderboard -> download -> predict."""
from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


def make_classification_csv(n: int = 200) -> bytes:
    rng = np.random.default_rng(0)
    age = rng.integers(18, 70, n)
    income = rng.normal(60000, 20000, n).round(0)
    city = rng.choice(["NYC", "LA", "SF"], n)
    # Target correlated with income + age.
    score = (income / 20000) + (age / 25) + rng.normal(0, 0.5, n)
    purchased = np.where(score > np.median(score), "yes", "no")
    df = pd.DataFrame({"age": age, "income": income, "city": city, "purchased": purchased})
    return df.to_csv(index=False).encode()


def poll(client, headers, run_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        s = client.get(f"/api/runs/{run_id}/status", headers=headers).json()
        if s["status"] in ("done", "error"):
            return s
        time.sleep(0.5)
    raise TimeoutError("run did not finish")


def main() -> None:
    with TestClient(app) as client:
        reg = client.post(
            "/api/auth/register", json={"email": "ml@example.com", "password": "supersecret1"}
        )
        assert reg.status_code == 201, reg.text
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        # Upload a classification dataset.
        up = client.post(
            "/api/datasets",
            files={"file": ("people.csv", io.BytesIO(make_classification_csv()), "text/csv")},
            headers=headers,
        )
        assert up.status_code == 200, up.text
        ds_id = up.json()["id"]

        # Start an async training run.
        run = client.post(
            "/api/runs",
            json={"dataset_id": ds_id, "task_type": "classification", "target_col": "purchased"},
            headers=headers,
        )
        assert run.status_code == 201, run.text
        run_id = run.json()["id"]
        assert run.json()["status"] == "queued"
        print("run queued:", run_id)

        status = poll(client, headers, run_id)
        print("final status:", status["status"], "-", status["message"])
        assert status["status"] == "done", status

        # Leaderboard.
        lb = client.get(f"/api/runs/{run_id}/leaderboard", headers=headers).json()
        print("primary metric:", lb["primary_metric"])
        print("leaderboard:")
        for m in lb["models"]:
            score = m["metrics_json"].get(lb["primary_metric"])
            print(f"  #{m['rank']:>2} {m['model_name']:<22} {lb['primary_metric']}={score}")
        assert len(lb["models"]) >= 5
        best_id = lb["best_model_id"]
        assert best_id is not None

        # Model detail has eval plots.
        detail = client.get(f"/api/runs/{run_id}/models/{best_id}", headers=headers).json()
        assert "confusion_matrix" in detail["plots_json"], detail["plots_json"].keys()
        print("best model plots:", sorted(detail["plots_json"].keys()))

        # Download the best model artifact.
        dl = client.get(f"/api/runs/{run_id}/models/{best_id}/download", headers=headers)
        assert dl.status_code == 200 and len(dl.content) > 0
        print("downloaded artifact bytes:", len(dl.content))

        # Predict on new rows.
        new_rows = b"age,income,city\n30,50000,LA\n55,110000,NYC\n"
        pred = client.post(
            f"/api/runs/{run_id}/predict",
            files={"file": ("new.csv", io.BytesIO(new_rows), "text/csv")},
            headers=headers,
        )
        assert pred.status_code == 200, pred.text
        print("predictions:", pred.json()["predictions"])
        assert pred.json()["n"] == 2

    print("\nSMOKE_TRAIN_PASSED")


if __name__ == "__main__":
    main()
