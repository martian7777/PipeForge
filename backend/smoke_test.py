"""End-to-end smoke test: auth -> upload -> detect -> run (clean + EDA)."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app

CSV = b"""age,city,income,purchased
34,NYC,72000,yes
28,LA,54000,no
45,NYC,98000,yes
52,SF,120000,yes
23,LA,,no
34,NYC,72000,yes
"""


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

        # Create a run (cleaning + EDA).
        run_body = {
            "dataset_id": ds["id"],
            "task_type": "classification",
            "target_col": "purchased",
        }
        run = client.post("/api/runs", json=run_body, headers=headers)
        assert run.status_code == 201, run.text
        run_json = run.json()
        print("run status:", run_json["status"], "stage:", run_json["stage"])
        assert run_json["status"] == "done", run_json

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
