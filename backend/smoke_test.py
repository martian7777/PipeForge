"""End-to-end smoke test: auth -> upload -> detect -> async run (clean + EDA + train)."""
from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


def _csv() -> bytes:
    rng = np.random.default_rng(7)
    n = 40
    age = rng.integers(20, 65, n)
    income = rng.normal(70000, 15000, n).round(0)
    income[3] = np.nan  # exercise imputation
    city = rng.choice(["NYC", "LA", "SF"], n)
    purchased = np.where(income > np.nanmedian(income), "yes", "no")
    df = pd.DataFrame({"age": age, "city": city, "income": income, "purchased": purchased})
    return df.to_csv(index=False).encode()


CSV = _csv()


def _poll(client, headers, run_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        s = client.get(f"/api/runs/{run_id}/status", headers=headers).json()
        if s["status"] in ("done", "error"):
            return s
        time.sleep(0.5)
    raise TimeoutError("run did not finish")


def main() -> None:
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"

        # Unauthenticated upload must be rejected.
        anon = client.post("/api/datasets", files={"file": ("x.csv", io.BytesIO(CSV), "text/csv")})
        assert anon.status_code == 401, f"expected 401, got {anon.status_code}"

        # Register + get a token.
        reg = client.post(
            "/api/auth/register", json={"email": "demo@example.com", "password": "supersecret1"}
        )
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("registered + token acquired")

        # /me
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["email"] == "demo@example.com"

        # Upload (authenticated).
        r = client.post(
            "/api/datasets",
            files={"file": ("people.csv", io.BytesIO(CSV), "text/csv")},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        ds = r.json()
        print("uploaded:", ds["id"], f"{ds['n_rows']}x{ds['n_cols']}")

        # Detect.
        d = client.post(f"/api/datasets/{ds['id']}/detect", headers=headers).json()
        print("suggested task:", d["suggested_task"])

        # Create an async run (cleaning + EDA + training).
        run_body = {
            "dataset_id": ds["id"],
            "task_type": "classification",
            "target_col": "purchased",
        }
        run = client.post("/api/runs", json=run_body, headers=headers)
        assert run.status_code == 201, run.text
        run_json = run.json()
        assert run_json["status"] == "queued", run_json
        final = _poll(client, headers, run_json["id"])
        print("run finished:", final["status"], "-", final["message"])
        assert final["status"] == "done", final

        # EDA payload.
        eda = client.get(f"/api/runs/{run_json['id']}/eda", headers=headers).json()
        print("eda summary:", eda["summary"]["n_rows"], "rows,", len(eda["charts"]), "charts")
        assert len(eda["charts"]) > 0
        chart_kinds = sorted({c["kind"] for c in eda["charts"]})
        print("chart kinds:", chart_kinds)
        assert eda["report_url"]

        # HTML report is served.
        rep = client.get(f"/api/runs/{run_json['id']}/report", headers=headers)
        assert rep.status_code == 200 and b"EDA Report" in rep.content

        # Validation: bad task/target should 422.
        bad = client.post(
            "/api/runs",
            json={"dataset_id": ds["id"], "task_type": "regression"},
            headers=headers,
        )
        assert bad.status_code == 422, bad.text

    print("\nSMOKE_TEST_PASSED")


if __name__ == "__main__":
    main()
