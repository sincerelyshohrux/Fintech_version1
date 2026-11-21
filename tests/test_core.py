from datetime import date

from app.config import settings
from app.core.data import build_profiles
from app.core.health import health_score
from app.core.osish import interest, treasury
from app.core.qalqon import detect, parse_csv
from app.core.shifo import annuity_payment, debt_overview
from app.security.pii import Redactor, StreamRestorer, mask_card
from app.security.policy import decide

TODAY = settings.today()
P = build_profiles(TODAY)


def _tx(d, desc, amt):
    return {"date": d, "description": desc, "amount": amt}


# ---------------- Qalqon rules
def test_aziza_findings():
    q = detect(P["aziza"]["statement"], P["aziza"]["usage"], TODAY, "4421")
    flagged = {f["id"]: f for f in q["findings"] if f["level"] != "past"}
    assert len(flagged) == 4
    assert q["potential_monthly"] == 478_000
    assert any("R2" in f["rules"] for f in flagged.values())   # trial
    assert any("R3" in f["rules"] for f in flagged.values())   # duplicate channel
    assert any("R4" in f["rules"] for f in flagged.values())   # price hike
    assert any("R5" in f["rules"] for f in flagged.values())   # unused gym


def test_trial_rule():
    st = [_tx("2026-09-02", "NETFLIX.COM", -1), _tx("2026-09-16", "NETFLIX.COM", -99_000),
          _tx("2026-10-16", "NETFLIX.COM", -99_000)]
    f = detect(st, {}, date(2026, 11, 1))["findings"][0]
    assert "R2" in f["rules"] and f["level"] == "yuqori" and f["monthly_saving"] == 99_000


def test_price_hike_saving_is_delta():
    st = [_tx(f"2026-{m:02d}-10", "MEGOGO", -a) for m, a in ((7, 39_000), (8, 39_000), (9, 39_000), (10, 49_000))]
    f = detect(st, {}, date(2026, 10, 20))["findings"][0]
    assert f["rules"] == ["R4"] and f["monthly_saving"] == 10_000


def test_double_charge_within_3_days():
    st = [_tx("2026-10-01", "SPOTIFY", -50_000), _tx("2026-10-02", "SPOTIFY", -50_000)]
    f = detect(st, {}, date(2026, 10, 20))["findings"][0]
    assert "R3" in f["rules"]


def test_irregular_spending_is_not_subscription():
    st = [_tx("2026-08-01", "KORZINKA", -120_000), _tx("2026-08-31", "KORZINKA", -310_000), _tx("2026-09-30", "KORZINKA", -75_000)]
    assert detect(st, {}, date(2026, 10, 20))["findings"] == []


def test_essential_is_low():
    st = [_tx(f"2026-{m:02d}-05", "BEELINE UZ", -60_000) for m in (8, 9, 10)]
    f = detect(st, {}, date(2026, 10, 20))["findings"][0]
    assert f["level"] == "past" and f["monthly_saving"] == 0


def test_parse_csv_validation():
    rows = parse_csv("date,description,amount\n21.10.2026,NETFLIX,-99000\n2026-10-01,SALARY,5000000\n")
    assert rows[0]["date"] == "2026-10-01" and rows[1]["amount"] == -99_000
    for bad in ("a,b\n1,2", "date,description,amount\nxx,Y,1", "date,description,amount\n"):
        try:
            parse_csv(bad)
            assert False, bad
        except ValueError:
            pass


# ---------------- O'sish
def test_interest():
    assert interest(64_300_000, 0.17, 7) == 209_636
    assert interest(0, 0.2, 30) == 0


def test_business_treasury_respects_payment_date():
    t = treasury(P["salomat"], TODAY, 0.15, [])
    rec = t["recommendation"]
    assert rec["instrument_id"] == "dep7" and rec["amount"] == 64_300_000 and rec["expected_earnings"] == 209_636
    assert rec["return_date"] < rec["payment_date"]
    inel = {i["id"] for i in t["instruments"] if not i["eligible"]}
    assert {"dep30", "bond28"} <= inel
    assert t["idle_cash"] % 100_000 == 0


def test_personal_treasury():
    t = treasury(P["aziza"], TODAY, 0.15, [])
    assert t["recommendation"]["instrument_id"] == "omonat30"
    assert t["recommendation"]["amount"] == 3_900_000


def test_deposit_removes_idle_cash():
    t = treasury(P["salomat"], TODAY, 0.15, [])
    rec = t["recommendation"]
    dep = [{"amount": rec["amount"], "return_date": rec["return_date"], "instrument_id": rec["instrument_id"], "expected_earnings": rec["expected_earnings"]}]
    assert treasury(P["salomat"], TODAY, 0.15, dep)["idle_cash"] < 100_000


def test_bigger_buffer_means_less_idle():
    a = treasury(P["salomat"], TODAY, 0.10, [])["idle_cash"]
    b = treasury(P["salomat"], TODAY, 0.30, [])["idle_cash"]
    assert b < a


# ---------------- Shifo & health
def test_annuity():
    assert annuity_payment(2_400_000, 0, 6) == 400_000
    assert 600_000 < annuity_payment(11_500_000, 0.24, 18) < 800_000


def test_debt_order():
    d = debt_overview(P["aziza"]["loans"], P["aziza"]["monthly_income"])
    assert d["avalanche_order"][0] == d["most_expensive"]
    assert 0 < d["dti"] < 1


def test_health_improves_when_resolved():
    q = detect(P["aziza"]["statement"], P["aziza"]["usage"], TODAY, "4421")
    t = treasury(P["aziza"], TODAY, 0.15, [])
    before = health_score(P["aziza"], q, t, set())["score"]
    flagged = {f["id"] for f in q["findings"] if f["level"] != "past"}
    after = health_score(P["aziza"], q, t, flagged)["score"]
    assert 0 <= before < after <= 100


# ---------------- Security
def test_pii_redaction_roundtrip():
    r = Redactor(["Aziza Karimova"])
    text = "Aziza Karimova, karta 8600 1234 5678 4421, tel +998 90 123 45 67, a@b.uz"
    red = r.redact(text)
    for secret in ("Aziza", "8600 1234", "123 45 67", "a@b.uz"):
        assert secret not in red
    assert r.restore(red) == text


def test_stream_restorer_handles_split_tokens():
    r = Redactor(["Aziza Karimova"])
    red = r.redact("Hurmat bilan, Aziza Karimova")
    sr = StreamRestorer(r)
    out = "".join(sr.feed(red[i:i + 3]) for i in range(0, len(red), 3)) + sr.flush()
    assert out == "Hurmat bilan, Aziza Karimova"


def test_mask_card():
    assert mask_card("8600 1234 5678 4421").endswith("4421") and "1234" not in mask_card("8600 1234 5678 4421")


def test_policy():
    assert decide("open_deposit", 100, "advice", 10**9)["status"] == "advice"
    assert decide("open_deposit", 100, "one_click", 10**9)["status"] == "proposed"
    assert decide("open_deposit", 100, "auto", 500)["status"] == "auto_execute"
    assert decide("open_deposit", 1000, "auto", 500)["status"] == "proposed"
    assert decide("prepay_loan", 100, "auto", 500)["status"] == "proposed"  # not in allowlist
