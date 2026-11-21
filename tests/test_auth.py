from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db
from app.core import cards
from app.main import app
from app.security.otp import OtpError, OtpService


# ---------------- pure validation
def test_luhn_and_type():
    assert cards.luhn_ok("9860 3500 1234 4825") and cards.luhn_ok("8600123456784427")
    assert not cards.luhn_ok("9860350012344821") and not cards.luhn_ok("1234")
    assert cards.card_type("8600 1234") == "uzcard" and cards.card_type("9860") == "humo" and cards.card_type("4111") is None


def test_expiry():
    today = date(2026, 11, 21)
    assert cards.expiry_ok(11, 26, today)          # current month is valid
    assert not cards.expiry_ok(10, 26, today)      # past
    assert not cards.expiry_ok(13, 28, today)
    assert cards.expiry_ok(1, 30, today)


def test_names():
    assert cards.name_ok("O'g'iloy") and cards.name_ok("Gʻulom") and cards.name_ok("Анна-Мария")
    assert not cards.name_ok("A") and not cards.name_ok("Aziza1") and not cards.name_ok("x@y")
    assert cards.holder_matches("AZIZA KARIMOVA", "Aziza", "Karimova")
    assert cards.holder_matches("karimova  aziza", "Aziza", "Karimova")          # order + spaces
    assert cards.holder_matches("GULOM TOSHMATOV", "Gʻulom", "Toshmatov")        # apostrophe variants
    assert not cards.holder_matches("AZIZ KARIMOV", "Aziza", "Karimova")


def test_phone():
    assert cards.normalize_phone("+998 90 123 45 67") == "998901234567"
    assert cards.normalize_phone("901234567") == "998901234567"
    assert cards.normalize_phone("+7 900 123 45 67") is None
    assert cards.mask_phone("998901234567") == "+998 90 *** ** 67"


# ---------------- OTP service
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_otp_success_and_single_use():
    clk = Clock()
    o = OtpService(clock=clk)
    code = o.issue("k")
    assert len(code) == 6 and code.isdigit()
    o.verify("k", code)
    with pytest.raises(OtpError):
        o.verify("k", code)  # consumed


def test_otp_hash_only_storage():
    o = OtpService(clock=Clock())
    code = o.issue("k")
    assert code.encode() not in o._entries["k"].digest


def test_otp_expiry():
    clk = Clock()
    o = OtpService(clock=clk)
    code = o.issue("k")
    clk.t += 301
    with pytest.raises(OtpError) as e:
        o.verify("k", code)
    assert e.value.code == "expired"


def test_otp_lockout_after_3_wrong():
    clk = Clock()
    o = OtpService(clock=clk)
    code = o.issue("k")
    wrong = "000000" if code != "000000" else "111111"
    for left in (2, 1):
        with pytest.raises(OtpError) as e:
            o.verify("k", wrong)
        assert e.value.attempts_left == left
    with pytest.raises(OtpError) as e:
        o.verify("k", wrong)
    assert e.value.code == "locked"
    with pytest.raises(OtpError) as e:
        o.issue("k")
    assert e.value.code == "locked"
    clk.t += 301
    assert o.issue("k")


def test_otp_resend_cooldown_and_limit():
    clk = Clock()
    o = OtpService(clock=clk)
    o.issue("k")
    with pytest.raises(OtpError) as e:
        o.issue("k")
    assert e.value.code == "cooldown"
    for _ in range(3):
        clk.t += 61
        o.issue("k")
    clk.t += 61
    with pytest.raises(OtpError) as e:
        o.issue("k")
    assert e.value.code == "send_limit"


# ---------------- full onboarding flow
def _code(r):
    return [w.rstrip(".") for w in r["demo_sms"].split() if w.rstrip(".").isdigit() and len(w.rstrip(".")) == 6][0]


def test_onboarding_flow_to_wipe():
    db.init_db()
    c = TestClient(app)
    assert c.get("/api/auth/me").json()["stage"] == "phone"
    assert c.post("/api/auth/phone", json={"phone": "123"}).status_code == 400
    r = c.post("/api/auth/phone", json={"phone": "+998 93 111 22 33"}).json()
    assert r["state"]["stage"] == "otp"
    assert c.post("/api/auth/profile", json={"first": "Ali", "last": "Valiyev"}).status_code == 409  # cannot skip OTP
    assert c.post("/api/auth/otp", json={"code": _code(r)}).json()["stage"] == "profile"
    assert c.post("/api/auth/profile", json={"first": "A1", "last": "Valiyev"}).status_code == 400
    assert c.post("/api/auth/profile", json={"first": "Ali", "last": "Valiyev"}).json()["stage"] == "card"
    assert c.get("/api/auth/me").json()["mode"] is None                      # dashboard still locked
    card = {"last4": "4427", "type": "uzcard", "exp_month": 12, "exp_year": 28, "holder": "VALIYEV ALI"}
    assert c.post("/api/auth/card", json=card | {"exp_month": 1, "exp_year": 20}).status_code == 400
    assert c.post("/api/auth/card", json=card | {"holder": "Boshqa Odam"}).status_code == 400
    assert c.post("/api/auth/card", json=card | {"type": "visa"}).status_code == 422
    r = c.post("/api/auth/card", json=card).json()
    assert c.post("/api/auth/card/otp", json={"code": _code(r)}).json()["stage"] == "setup"
    assert c.post("/api/auth/setup", json={"consent": False, "balance": 1}).status_code == 400
    assert c.post("/api/auth/setup", json={"consent": True}).status_code == 400       # balance or CSV required
    st = c.post("/api/auth/setup", json={"consent": True, "balance": 3_000_000}).json()
    assert st["stage"] == "ready" and st["card"]["label"] == "UzCard •••• 4427"
    pid = st["pid"]
    # Only the own profile is reachable; demo profiles are not
    assert c.get(f"/api/home/{pid}").status_code == 200
    assert c.get("/api/home/aziza").status_code == 404
    o = c.get(f"/api/osish/{pid}").json()
    assert set(o["missing"]) == {"oylik daromad", "oylik kuni", "zarur xarajatlar"}
    c.post("/api/auth/finance", json={"monthly_income": 8_000_000, "payday": 10, "essentials": 4_000_000})
    assert "missing" not in c.get(f"/api/osish/{pid}").json()
    sec = c.get(f"/api/security/{pid}").json()["stored"]
    assert sec["card"]["number"] == "saqlanmaydi" and "4427" == sec["card"]["last4"]
    # Wipe
    c.post("/api/auth/logout")
    assert c.get(f"/api/home/{pid}").status_code == 401
    assert c.get("/api/auth/me").json()["stage"] == "phone"
    assert db.get_settings(pid)["autonomy"] == "one_click"  # defaults again → stored rows were deleted


def test_otp_lockout_via_api():
    c = TestClient(app)
    c.post("/api/auth/phone", json={"phone": "+998 99 777 66 55"})
    codes = [c.post("/api/auth/otp", json={"code": "999999"}).status_code for _ in range(3)]
    assert codes[-1] == 429
    assert c.post("/api/auth/otp", json={"code": "123456"}).json()["detail"]["code"] == "locked"


def test_csv_in_onboarding_stays_in_memory():
    c = TestClient(app)
    r = c.post("/api/auth/phone", json={"phone": "+998 97 000 11 22"}).json()
    c.post("/api/auth/otp", json={"code": _code(r)})
    c.post("/api/auth/profile", json={"first": "Dilnoza", "last": "Rahimova"})
    r = c.post("/api/auth/card", json={"last4": "4825", "type": "humo", "exp_month": 6, "exp_year": 29, "holder": "Rahimova Dilnoza"}).json()
    c.post("/api/auth/card/otp", json={"code": _code(r)})
    with open("static/sample_statement.csv", "rb") as f:
        assert c.post("/api/auth/statement", files={"file": ("k.csv", f, "text/csv")}).json()["rows"] > 100
    pid = c.post("/api/auth/setup", json={"consent": True}).json()["pid"]
    q = c.get(f"/api/qalqon/{pid}").json()
    assert q["loaded"] and q["source"] == "csv" and q["flagged_count"] >= 3
    assert db.get_upload(pid) is None  # never written to SQLite
