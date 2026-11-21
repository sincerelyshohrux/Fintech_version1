"""FinPilot FastAPI application."""
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import auth, db, services, sessions
from app.agent.agent import last_payload_by_profile, run_agent
from app.agent.presets import resolve_preset
from app.config import BASE_DIR, settings
from app.core.qalqon import parse_csv
from app.security import policy, ratelimit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = BASE_DIR / "static"
MAX_CSV_BYTES = 1_000_000


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="FinPilot", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.include_router(auth.router)


def _session(request: Request) -> sessions.Session:
    s = auth.current(request)
    if not s or s.stage != "ready":
        raise HTTPException(401, "Avval tizimga kiring")
    return s


def _pid(pid: str, request: Request) -> str:
    """Every module endpoint is scoped to the caller's session: demo session → demo profiles, user → own profile."""
    if pid not in _session(request).allowed_pids:
        raise HTTPException(404, "Profil topilmadi")
    return pid


def _action(action_id: int, request: Request) -> dict:
    a = db.action_get(action_id)
    if not a or a["profile_id"] not in _session(request).allowed_pids:
        raise HTTPException(404, "Amal topilmadi")
    return a


@app.exception_handler(services.ActionError)
async def _action_error(_: Request, exc: services.ActionError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ------------------------------------------------------------------ pages & meta

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/meta")
def meta():
    return {"ai_enabled": settings.ai_enabled, "model": settings.claude_model, "today": settings.today().isoformat(),
            "profiles": [{"id": p["id"], "title": p["title"], "kind": p["kind"]} for p in services.profiles().values()],
            "autonomy_levels": policy.LEVELS, "auto_allowlist": sorted(policy.AUTO_ALLOWLIST)}


@app.get("/api/home/{pid}")
def home(pid: str, request: Request):
    return services.home(_pid(pid, request))


# ------------------------------------------------------------------ settings & consent

class SettingsIn(BaseModel):
    autonomy: str = Field(pattern="^(advice|one_click|auto)$")
    auto_limit: int = Field(ge=0, le=1_000_000_000)


@app.get("/api/settings/{pid}")
def get_settings(pid: str, request: Request):
    return db.get_settings(_pid(pid, request))


@app.put("/api/settings/{pid}")
def put_settings(pid: str, body: SettingsIn, request: Request):
    s = db.put_settings(_pid(pid, request), body.autonomy, body.auto_limit)
    db.audit(pid, "user", "settings.autonomy", {"autonomy": body.autonomy, "auto_limit": body.auto_limit})
    return s


@app.get("/api/consent/{pid}")
def get_consent(pid: str, request: Request):
    return services.consent_get(_pid(pid, request))


@app.post("/api/consent/{pid}/{state}")
def set_consent(pid: str, state: str, request: Request):
    if state not in ("grant", "revoke"):
        raise HTTPException(400, "grant yoki revoke")
    c = services.consent_set(_pid(pid, request), state == "grant")
    db.audit(pid, "user", f"consent.{state}", {"scopes": ["tranzaksiyalar", "hisoblar", "kreditlar", "AI tahlil"]})
    return c


def _require_consent(pid: str) -> None:
    if not services.consent_get(pid)["granted"]:
        raise HTTPException(403, "Avval ma'lumotlarni tahlil qilishga rozilik bering")


# ------------------------------------------------------------------ modules

@app.post("/api/qalqon/{pid}/load-sample")
def qalqon_load(pid: str, request: Request):
    _require_consent(_pid(pid, request))
    if pid not in sessions.DEMO_PIDS:
        raise HTTPException(400, "Namuna ko'chirma faqat demo profillar uchun. O'z CSV faylingizni yuklang")
    db.set_upload(pid, "sample", None)
    db.audit(pid, "user", "statement.loaded", {"source": "bank (90 kun)"})
    return services.qalqon(pid)


@app.post("/api/qalqon/{pid}/upload")
async def qalqon_upload(pid: str, request: Request, file: UploadFile = File(...)):
    _require_consent(_pid(pid, request))
    rows = await _read_csv(file)
    us = services.user_session(pid)
    if us:
        us.statement, us.statement_name = rows, (file.filename or "")[:60]  # memory only
    else:
        db.set_upload(pid, "csv", rows)
    db.audit(pid, "user", "statement.uploaded", {"rows": len(rows), "file": (file.filename or "")[:60]})
    return services.qalqon(pid)


async def _read_csv(file: UploadFile) -> list[dict]:
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(413, "Fayl hajmi 1 MB dan oshmasligi kerak")
    try:
        return parse_csv(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise HTTPException(400, "Fayl UTF-8 formatida bo'lishi kerak")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/auth/statement")
async def onboarding_statement(request: Request, file: UploadFile = File(...)):
    """Onboarding step 7: CSV statement, kept in session memory only."""
    s = auth.current(request)
    if not s or s.stage not in ("setup", "ready") or s.mode == "demo":
        raise HTTPException(409, "Bu qadam hozir mavjud emas")
    rows = await _read_csv(file)
    s.statement, s.statement_name = rows, (file.filename or "")[:60]
    db.audit(s.uid, "user", "statement.uploaded", {"rows": len(rows)})
    return {"rows": len(rows), "state": auth.state(s)}


@app.get("/api/qalqon/{pid}")
def qalqon(pid: str, request: Request):
    return services.qalqon(_pid(pid, request))


@app.get("/api/osish/{pid}")
def osish(pid: str, request: Request, buffer_pct: float | None = None):
    return services.osish(_pid(pid, request), buffer_pct)


@app.get("/api/shifo/{pid}")
def shifo(pid: str, request: Request):
    return services.shifo(_pid(pid, request))


class LoanIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    principal: int = Field(gt=0, le=10_000_000_000)
    rate: float = Field(ge=0, le=1.5)
    months_left: int = Field(ge=1, le=360)


@app.post("/api/shifo/{pid}/loans")
def add_loan(pid: str, body: LoanIn, request: Request):
    us = services.user_session(_pid(pid, request))
    if not us:
        raise HTTPException(400, "Demo profil kreditlarini o'zgartirib bo'lmaydi")
    if len(us.loans) >= 10:
        raise HTTPException(400, "Ko'pi bilan 10 ta kredit")
    us.loans.append({"id": f"k{len(us.loans) + 1}", **body.model_dump()})
    db.audit(pid, "user", "loan.added", {"rate": body.rate, "months_left": body.months_left})
    return services.shifo(pid)


@app.get("/api/meros/{pid}")
def meros(pid: str, request: Request):
    return services.meros(_pid(pid, request))


# ------------------------------------------------------------------ actions

class PrepareIn(BaseModel):
    profile_id: str
    type: str
    params: dict = {}


@app.post("/api/actions/prepare")
async def prepare(body: PrepareIn, request: Request):
    _require_consent(_pid(body.profile_id, request))
    if body.type not in services.ACTION_LABELS:
        raise HTTPException(400, "Noma'lum amal turi")
    return await services.prepare(body.profile_id, body.type, body.params, created_by="user")


@app.post("/api/actions/{action_id}/confirm")
async def confirm(action_id: int, request: Request):
    a = _action(action_id, request)
    db.audit(a["profile_id"], "user", "action.confirmed", {"action_id": action_id})
    return await services.execute(action_id, actor="user")


@app.post("/api/actions/{action_id}/reject")
def reject(action_id: int, request: Request):
    _action(action_id, request)
    return services.reject(action_id)


@app.post("/api/actions/{action_id}/undo")
async def undo(action_id: int, request: Request):
    _action(action_id, request)
    return await services.undo(action_id)


@app.get("/api/actions/{pid}")
def actions(pid: str, request: Request):
    return db.actions_list(_pid(pid, request))


# ------------------------------------------------------------------ audit & security

@app.get("/api/audit")
def audit(request: Request, limit: int = 200):
    """The chain is global (so it can be verified), but each session only sees its own entries."""
    mine = set(_session(request).allowed_pids) | {"system"}
    return [r for r in db.audit_list(2000, None) if r["profile_id"] in mine][:min(limit, 500)]


@app.get("/api/audit/verify")
def audit_verify(request: Request):
    _session(request)
    return db.audit_verify()


@app.post("/api/audit/tamper-demo")
def audit_tamper(request: Request):
    _session(request)
    return db.audit_tamper_demo()


@app.post("/api/audit/restore-demo")
def audit_restore(request: Request):
    _session(request)
    return db.audit_restore_demo()


@app.get("/api/security/{pid}")
def security(pid: str, request: Request):
    s = _session(request)
    return {"consent": services.consent_get(_pid(pid, request)), "ai_enabled": settings.ai_enabled,
            "last_payload": last_payload_by_profile.get(pid, []), "audit": db.audit_verify(),
            "mode": s.mode, "demo_mode": settings.demo_mode, "sms_provider": settings.sms_provider,
            "stored": ({"card": (s.card or {}) | {"number": "saqlanmaydi"}, "phone": auth.cards.mask_phone(s.phone),
                        "statement_rows": len(s.statement or []), "where": "faqat server xotirasi (sessiya)"}
                       if s.mode == "user" else None)}


@app.post("/api/demo/reset")
def demo_reset(request: Request):
    if _session(request).mode != "demo":
        raise HTTPException(403, "Faqat demo rejimida")
    db.reset_all()
    last_payload_by_profile.clear()
    db.audit("system", "system", "demo.reset", {"note": "demo holati tozalandi"})
    return {"ok": True}


# ------------------------------------------------------------------ AI agent (SSE)

class AgentIn(BaseModel):
    profile_id: str
    message: str | None = Field(default=None, max_length=2000)
    preset: str | None = Field(default=None, max_length=80)
    conversation_id: str | None = Field(default=None, max_length=40)
    buffer_pct: float | None = Field(default=None, ge=0, le=0.5)


@app.post("/api/agent")
async def agent(body: AgentIn, request: Request):
    _require_consent(_pid(body.profile_id, request))
    client = request.client.host if request.client else "anon"
    if not ratelimit.allow(f"agent:{client}", limit=30, window=60):
        raise HTTPException(429, "Juda ko'p so'rov. Bir daqiqadan so'ng urinib ko'ring.")
    message, intent = resolve_preset(body.preset, body.message)
    if not message:
        raise HTTPException(400, "Savol bo'sh")

    async def events():
        try:
            async for ev in run_agent(body.profile_id, message, intent, body.conversation_id,
                                      {"buffer_pct": body.buffer_pct}):
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
        except Exception:  # never leave the UI hanging
            logging.exception("agent stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Kutilmagan xato yuz berdi'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'redacted_payload': []})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
