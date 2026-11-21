from fastapi.testclient import TestClient

from app import db
from app.main import app

c = TestClient(app)


def setup_module():
    db.init_db()
    assert c.get("/api/home/aziza").status_code == 401  # no session → nothing
    c.post("/api/auth/demo")
    c.post("/api/demo/reset")


def test_consent_required():
    c.post("/api/consent/aziza/revoke")
    assert c.post("/api/qalqon/aziza/load-sample").status_code == 403
    assert c.post("/api/agent", json={"profile_id": "aziza", "message": "salom"}).status_code == 403
    assert c.post("/api/consent/aziza/grant").status_code == 200


def test_full_flow_block_then_audit():
    c.post("/api/consent/aziza/grant")
    q = c.post("/api/qalqon/aziza/load-sample").json()
    assert q["potential_monthly"] == 478_000
    score0 = c.get("/api/home/aziza").json()["health"]["score"]
    gym = next(f for f in q["findings"] if "R5" in f["rules"])
    a = c.post("/api/actions/prepare", json={"profile_id": "aziza", "type": "block_merchant",
                                              "params": {"finding_id": gym["id"]}}).json()
    assert a["status"] == "proposed"
    done = c.post(f"/api/actions/{a['id']}/confirm").json()
    assert done["status"] == "executed"
    assert c.get("/api/home/aziza").json()["health"]["score"] > score0
    assert c.get("/api/qalqon/aziza").json()["realized_monthly"] > 0
    assert c.get("/api/audit/verify").json()["ok"]


def test_auto_deposit_and_undo():
    c.post("/api/consent/salomat/grant")
    c.put("/api/settings/salomat", json={"autonomy": "auto", "auto_limit": 100_000_000})
    rec = c.get("/api/osish/salomat").json()["recommendation"]
    a = c.post("/api/actions/prepare", json={"profile_id": "salomat", "type": "open_deposit",
                                              "params": {"instrument_id": rec["instrument_id"], "amount": rec["amount"]}}).json()
    assert a["status"] == "executed" and a["mode"] == "auto"
    assert c.get("/api/osish/salomat").json()["idle_cash"] < 100_000
    assert c.post(f"/api/actions/{a['id']}/undo").json()["status"] == "undone"
    assert c.get("/api/osish/salomat").json()["idle_cash"] == rec["amount"]


def test_deposit_cannot_exceed_idle_cash():
    c.put("/api/settings/salomat", json={"autonomy": "one_click", "auto_limit": 0})
    r = c.post("/api/actions/prepare", json={"profile_id": "salomat", "type": "open_deposit",
                                              "params": {"instrument_id": "dep7", "amount": 10**12}})
    assert r.status_code == 400


def test_tamper_detection():
    assert c.get("/api/audit/verify").json()["ok"]
    c.post("/api/audit/tamper-demo")
    assert not c.get("/api/audit/verify").json()["ok"]
    c.post("/api/audit/restore-demo")
    assert c.get("/api/audit/verify").json()["ok"]


def test_offline_agent_letter_streams_and_redacts():
    c.post("/api/consent/aziza/grant")
    c.post("/api/qalqon/aziza/load-sample")
    with c.stream("POST", "/api/agent", json={"profile_id": "aziza", "preset": "letter:yandex-plus-r2r5"}) as r:
        body = "".join(r.iter_text())
    assert '"mode": "offline"' in body or '"mode":"offline"' in body
    assert '"type": "done"' in body or '"type":"done"' in body


def test_csv_upload_limits():
    c.post("/api/consent/aziza/grant")
    bad = c.post("/api/qalqon/aziza/upload", files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert bad.status_code == 400
    ok = c.post("/api/qalqon/aziza/upload", files={"file": ("x.csv",
              b"date,description,amount\n2026-09-01,NETFLIX,-99000\n2026-10-01,NETFLIX,-99000\n2026-11-01,NETFLIX,-99000\n", "text/csv")})
    assert ok.status_code == 200 and ok.json()["source"] == "csv"
