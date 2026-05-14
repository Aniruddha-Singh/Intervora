import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI
from pydantic import BaseModel, EmailStr, Field

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "backend" / "interview_pro.db"
MODEL_PATH = PROJECT_ROOT / "yolov8n.pt"
JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME_HOURS = 24
PASSWORD_ITERATIONS = 120_000
ALLOWED_SIGNUP_ROLES = {"candidate", "admin"}

load_dotenv(PROJECT_ROOT / ".env")

ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}

groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise RuntimeError("GROQ_API_KEY is missing. Add it to .env before starting the backend.")

auth_secret = os.getenv("AUTH_SECRET_KEY") or hashlib.sha256(
    f"{groq_api_key}-auth".encode("utf-8")
).hexdigest()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=groq_api_key,
)

app = FastAPI(title="Interview Pro API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer(auto_error=False)


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class StartInterviewRequest(BaseModel):
    target_role: str = Field(min_length=2, max_length=120)
    proctoring_enabled: bool = True


class InterviewState(BaseModel):
    interview_id: str = Field(min_length=8)
    target_role: str
    messages: List[Message]
    proctoring_enabled: bool = True
    proctor_summary: Optional[Dict[str, Any]] = None


class UserRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="candidate")


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class InterviewResponse(BaseModel):
    interview_id: str
    messages: List[Message]
    assistant_message: str


class InterviewHistoryItem(BaseModel):
    id: str
    target_role: str
    status: str
    score: Optional[int] = None
    started_at: str
    completed_at: Optional[str] = None
    proctoring_enabled: bool
    user_name: Optional[str] = None
    user_email: Optional[str] = None


class AdminUserItem(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: str
    interview_count: int = 0


class AdminDashboardResponse(BaseModel):
    total_users: int
    total_admins: int
    total_candidates: int
    total_interviews: int
    completed_interviews: int
    active_interviews: int
    average_score: Optional[float] = None
    flagged_interviews: int
    recent_users: List[AdminUserItem]
    recent_interviews: List[InterviewHistoryItem]


class ProctorAnalyzeResponse(BaseModel):
    status: Literal[
        "clear",
        "no_face",
        "multiple_faces",
        "low_visibility",
        "phone_detected",
        "restricted_object",
    ]
    detail: str
    faces: int
    brightness: float
    sharpness: float
    frame_hash: str
    analyzed_at: float
    phones: int = 0
    persons: int = 0
    objects: List[str] = []


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('candidate', 'admin')),
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interviews (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                target_role TEXT NOT NULL,
                status TEXT NOT NULL,
                score INTEGER,
                proctoring_enabled INTEGER NOT NULL DEFAULT 1,
                messages_json TEXT NOT NULL,
                proctor_summary_json TEXT,
                feedback_report TEXT,
                closing_text TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )


def sync_admin_allowlist() -> None:
    if not ADMIN_EMAILS:
        return

    placeholders = ",".join("?" for _ in ADMIN_EMAILS)
    with get_db_connection() as connection:
        connection.execute(
            f"UPDATE users SET role = 'admin' WHERE lower(email) IN ({placeholders})",
            tuple(sorted(ADMIN_EMAILS)),
        )


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    sync_admin_allowlist()


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def create_token(user: Dict[str, Any]) -> str:
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=TOKEN_LIFETIME_HOURS)).timestamp()),
    }
    signing_input = ".".join(
        [
            base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(auth_secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{base64url_encode(signature)}"


def decode_token(token: str) -> Dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    signing_input = f"{header_part}.{payload_part}"
    expected_signature = hmac.new(
        auth_secret.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_signature, base64url_decode(signature_part)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature.")

    payload = json.loads(base64url_decode(payload_part))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    return payload


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"{PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        iterations_text, salt_hex, stored_digest = password_hash.split("$", 2)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations_text),
    )
    return hmac.compare_digest(digest.hex(), stored_digest)


def row_to_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"],
    }


def user_response_from_row(row: sqlite3.Row) -> UserResponse:
    return UserResponse(**row_to_user(row))


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with get_db_connection() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower(),),
        ).fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    with get_db_connection() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def sync_user_admin_role(user_row: sqlite3.Row) -> sqlite3.Row:
    email = user_row["email"].lower()
    should_be_admin = email in ADMIN_EMAILS
    current_role = user_row["role"]

    if should_be_admin and current_role != "admin":
        with get_db_connection() as connection:
            connection.execute(
                "UPDATE users SET role = 'admin' WHERE id = ?",
                (user_row["id"],),
            )
        refreshed_user = get_user_by_id(user_row["id"])
        return refreshed_user if refreshed_user is not None else user_row

    return user_row


def resolve_signup_role(email: str, requested_role: str) -> str:
    normalized_role = requested_role.lower().strip()
    if normalized_role not in ALLOWED_SIGNUP_ROLES:
        raise HTTPException(status_code=400, detail="Role must be candidate or admin.")

    with get_db_connection() as connection:
        user_count = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]

    if normalized_role == "admin":
        if user_count == 0 or email.lower() in ADMIN_EMAILS:
            return "admin"
        raise HTTPException(
            status_code=403,
            detail="Admin signup is restricted. Add the email to ADMIN_EMAILS to allow it.",
        )

    return "candidate"


def create_user(payload: UserRegisterRequest) -> sqlite3.Row:
    email = payload.email.lower()
    role = resolve_signup_role(email, payload.role)
    password_hash = hash_password(payload.password)
    created_at = utc_now_iso()

    try:
        with get_db_connection() as connection:
            connection.execute(
                """
                INSERT INTO users (name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.name.strip(), email, password_hash, role, created_at),
            )
            user_id = connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc

    user_row = get_user_by_id(user_id)
    if user_row is None:
        raise HTTPException(status_code=500, detail="User could not be created.")
    return sync_user_admin_role(user_row)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> sqlite3.Row:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    payload = decode_token(credentials.credentials)
    user_row = get_user_by_id(int(payload["sub"]))
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user_row


def require_admin(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return user


def clean_response_text(text: str) -> str:
    text = re.sub(r"^\d+[\.\)]\s*", "", text)
    text = re.sub(r"\(Note:.*?\)", "", text, flags=re.IGNORECASE)
    return text.strip()


def build_system_prompt(target_role: str) -> str:
    return f"""
You are a professional interviewer for a {target_role} role.

INSTRUCTIONS:
1. Start immediately by welcoming the candidate and asking for their introduction.
2. Do not say "Note:", "I will follow...", or "Okay". Just speak.
3. Ask relevant follow-up questions.
4. Refuse off-topic requests firmly but politely.
5. Keep responses concise, maximum 2 sentences.
6. If it is a developer role, ask coding questions only when useful.
""".strip()


def chat_completion(messages: List[Dict[str, str]]) -> str:
    return client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
    ).choices[0].message.content


def get_face_cascade():
    if cv2 is None:
        raise HTTPException(
            status_code=503,
            detail="OpenCV is not installed. Install backend requirements to enable proctoring.",
        )
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def get_object_detector():
    if YOLO is None:
        return None
    if not hasattr(get_object_detector, "_model"):
        get_object_detector._model = YOLO(str(MODEL_PATH))
    return get_object_detector._model


def analyze_objects(frame: Any) -> Dict[str, object]:
    if cv2 is None or np is None:
        return {"persons": 0, "phones": 0, "restricted_objects": [], "objects": []}
    detector = get_object_detector()
    if detector is None:
        return {"persons": 0, "phones": 0, "restricted_objects": [], "objects": []}

    result = detector(frame, imgsz=320, conf=0.35, verbose=False)[0]
    labels: List[str] = []
    persons = 0
    phones = 0
    restricted_objects: List[str] = []
    tracked_restricted = {"cell phone", "laptop", "book", "remote"}

    if result.boxes is not None:
        for cls_index in result.boxes.cls.tolist():
            label = result.names[int(cls_index)]
            labels.append(label)
            if label == "person":
                persons += 1
            elif label == "cell phone":
                phones += 1
                restricted_objects.append(label)
            elif label in tracked_restricted:
                restricted_objects.append(label)

    return {
        "persons": persons,
        "phones": phones,
        "restricted_objects": sorted(set(restricted_objects)),
        "objects": labels,
    }


def summarize_proctoring(summary: Optional[Dict[str, Any]], enabled: bool) -> str:
    if not enabled:
        return "Proctor mode was disabled for this interview."
    if not summary:
        return "Proctor mode was enabled, but no webcam checks were recorded."

    stats = summary.get("stats", {})
    events = summary.get("events", [])
    total = sum(stats.values())
    suspicious = stats.get("no_face", 0) + stats.get("multiple_faces", 0) + stats.get("low_visibility", 0)
    suspicious += stats.get("phone_detected", 0) + stats.get("restricted_object", 0)

    lines = [
        "## Proctoring Summary",
        f"- Webcam checks processed: {total}",
        f"- Clear frames: {stats.get('clear', 0)}",
        f"- No-face flags: {stats.get('no_face', 0)}",
        f"- Multiple-face flags: {stats.get('multiple_faces', 0)}",
        f"- Low-visibility flags: {stats.get('low_visibility', 0)}",
        f"- Phone detections: {stats.get('phone_detected', 0)}",
        f"- Restricted-object detections: {stats.get('restricted_object', 0)}",
    ]
    if suspicious == 0:
        lines.append("- Overall result: No suspicious webcam events were detected.")
    else:
        lines.append("- Overall result: Review flagged moments before making any decision.")
    if events:
        lines.append("- Recent flagged events:")
        for event in events[-5:]:
            lines.append(f"  - {event.get('time', 'unknown')}: {event.get('detail', '')}")
    return "\n".join(lines)


def extract_score(report: str) -> Optional[int]:
    match = re.search(r"## Score:\s*(\d{1,3})/100", report)
    if not match:
        return None
    return int(match.group(1))


def load_interview_for_user(interview_id: str, user: sqlite3.Row) -> sqlite3.Row:
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT interviews.*, users.name AS user_name, users.email AS user_email
            FROM interviews
            JOIN users ON users.id = interviews.user_id
            WHERE interviews.id = ?
            """,
            (interview_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Interview not found.")
    if user["role"] != "admin" and row["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this interview.")
    return row


def save_interview(
    interview_id: str,
    user_id: int,
    target_role: str,
    status_value: str,
    messages: List[Dict[str, str]],
    proctoring_enabled: bool,
    proctor_summary: Optional[Dict[str, Any]] = None,
    report: Optional[str] = None,
    closing_text: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> None:
    now_iso = utc_now_iso()
    score = extract_score(report or "") if report else None
    with get_db_connection() as connection:
        connection.execute(
            """
            UPDATE interviews
            SET target_role = ?,
                status = ?,
                score = ?,
                proctoring_enabled = ?,
                messages_json = ?,
                proctor_summary_json = ?,
                feedback_report = ?,
                closing_text = ?,
                updated_at = ?,
                completed_at = COALESCE(?, completed_at)
            WHERE id = ? AND user_id = ?
            """,
            (
                target_role,
                status_value,
                score,
                int(proctoring_enabled),
                json.dumps(messages),
                json.dumps(proctor_summary) if proctor_summary else None,
                report,
                closing_text,
                now_iso,
                completed_at,
                interview_id,
                user_id,
            ),
        )


def history_row_to_item(row: sqlite3.Row) -> InterviewHistoryItem:
    return InterviewHistoryItem(
        id=row["id"],
        target_role=row["target_role"],
        status=row["status"],
        score=row["score"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        proctoring_enabled=bool(row["proctoring_enabled"]),
        user_name=row["user_name"] if "user_name" in row.keys() else None,
        user_email=row["user_email"] if "user_email" in row.keys() else None,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=AuthResponse)
def register(payload: UserRegisterRequest):
    user_row = create_user(payload)
    token = create_token(row_to_user(user_row))
    return AuthResponse(token=token, user=user_response_from_row(user_row))


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: UserLoginRequest):
    user_row = get_user_by_email(payload.email.lower())
    if user_row is None or not verify_password(payload.password, user_row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    user_row = sync_user_admin_role(user_row)
    token = create_token(row_to_user(user_row))
    return AuthResponse(token=token, user=user_response_from_row(user_row))


@app.get("/auth/me", response_model=UserResponse)
def me(user: sqlite3.Row = Depends(get_current_user)):
    user = sync_user_admin_role(user)
    return user_response_from_row(user)


@app.get("/api/interviews/mine", response_model=List[InterviewHistoryItem])
def my_interviews(user: sqlite3.Row = Depends(get_current_user)):
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT interviews.*, users.name AS user_name, users.email AS user_email
            FROM interviews
            JOIN users ON users.id = interviews.user_id
            WHERE interviews.user_id = ?
            ORDER BY interviews.started_at DESC
            """,
            (user["id"],),
        ).fetchall()
    return [history_row_to_item(row) for row in rows]


@app.get("/api/admin/interviews", response_model=List[InterviewHistoryItem])
def admin_interviews(admin: sqlite3.Row = Depends(require_admin)):
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT interviews.*, users.name AS user_name, users.email AS user_email
            FROM interviews
            JOIN users ON users.id = interviews.user_id
            ORDER BY interviews.started_at DESC
            LIMIT 50
            """
        ).fetchall()
    return [history_row_to_item(row) for row in rows]


@app.get("/api/admin/users", response_model=List[AdminUserItem])
def admin_users(admin: sqlite3.Row = Depends(require_admin)):
    del admin
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                users.id,
                users.name,
                users.email,
                users.role,
                users.created_at,
                COUNT(interviews.id) AS interview_count
            FROM users
            LEFT JOIN interviews ON interviews.user_id = users.id
            GROUP BY users.id
            ORDER BY users.created_at DESC
            LIMIT 50
            """
        ).fetchall()
    return [AdminUserItem(**dict(row)) for row in rows]


@app.get("/api/admin/dashboard", response_model=AdminDashboardResponse)
def admin_dashboard(admin: sqlite3.Row = Depends(require_admin)):
    del admin
    with get_db_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) AS total_admins,
                SUM(CASE WHEN role = 'candidate' THEN 1 ELSE 0 END) AS total_candidates
            FROM users
            """
        ).fetchone()
        interview_totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_interviews,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_interviews,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_interviews,
                AVG(score) AS average_score
            FROM interviews
            """
        ).fetchone()
        flagged = connection.execute(
            """
            SELECT COUNT(*) AS flagged_interviews
            FROM interviews
            WHERE proctor_summary_json IS NOT NULL
              AND (
                COALESCE(json_extract(proctor_summary_json, '$.stats.no_face'), 0) > 0 OR
                COALESCE(json_extract(proctor_summary_json, '$.stats.multiple_faces'), 0) > 0 OR
                COALESCE(json_extract(proctor_summary_json, '$.stats.low_visibility'), 0) > 0 OR
                COALESCE(json_extract(proctor_summary_json, '$.stats.phone_detected'), 0) > 0 OR
                COALESCE(json_extract(proctor_summary_json, '$.stats.restricted_object'), 0) > 0
              )
            """
        ).fetchone()
        recent_user_rows = connection.execute(
            """
            SELECT
                users.id,
                users.name,
                users.email,
                users.role,
                users.created_at,
                COUNT(interviews.id) AS interview_count
            FROM users
            LEFT JOIN interviews ON interviews.user_id = users.id
            GROUP BY users.id
            ORDER BY users.created_at DESC
            LIMIT 6
            """
        ).fetchall()
        recent_interview_rows = connection.execute(
            """
            SELECT interviews.*, users.name AS user_name, users.email AS user_email
            FROM interviews
            JOIN users ON users.id = interviews.user_id
            ORDER BY interviews.started_at DESC
            LIMIT 8
            """
        ).fetchall()

    average_score = interview_totals["average_score"]
    return AdminDashboardResponse(
        total_users=totals["total_users"] or 0,
        total_admins=totals["total_admins"] or 0,
        total_candidates=totals["total_candidates"] or 0,
        total_interviews=interview_totals["total_interviews"] or 0,
        completed_interviews=interview_totals["completed_interviews"] or 0,
        active_interviews=interview_totals["active_interviews"] or 0,
        average_score=round(average_score, 1) if average_score is not None else None,
        flagged_interviews=flagged["flagged_interviews"] or 0,
        recent_users=[AdminUserItem(**dict(row)) for row in recent_user_rows],
        recent_interviews=[history_row_to_item(row) for row in recent_interview_rows],
    )


@app.post("/api/interview/start", response_model=InterviewResponse)
def start_interview(payload: StartInterviewRequest, user: sqlite3.Row = Depends(get_current_user)):
    sys_prompt = build_system_prompt(payload.target_role)
    greeting = chat_completion(
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "Start the interview now. Output only the spoken greeting."},
        ]
    )
    greeting = clean_response_text(greeting)
    full_messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "assistant", "content": greeting},
    ]
    interview_id = uuid4().hex
    now_iso = utc_now_iso()

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO interviews (
                id, user_id, target_role, status, proctoring_enabled,
                messages_json, started_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interview_id,
                user["id"],
                payload.target_role.strip(),
                "active",
                int(payload.proctoring_enabled),
                json.dumps(full_messages),
                now_iso,
                now_iso,
            ),
        )

    return InterviewResponse(
        interview_id=interview_id,
        messages=[Message(**message) for message in full_messages],
        assistant_message=greeting,
    )


@app.post("/api/interview/respond", response_model=InterviewResponse)
def respond_to_interview(payload: InterviewState, user: sqlite3.Row = Depends(get_current_user)):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="Messages are required.")

    interview = load_interview_for_user(payload.interview_id, user)
    if interview["status"] == "completed":
        raise HTTPException(status_code=400, detail="This interview has already been completed.")

    messages = [message.model_dump() for message in payload.messages]
    if len(messages) == 36:
        messages.append(
            {
                "role": "system",
                "content": "You have gathered sufficient data. Ask 1-2 final questions and then conclude the interview.",
            }
        )

    response = clean_response_text(chat_completion(messages))
    messages.append({"role": "assistant", "content": response})
    save_interview(
        interview_id=payload.interview_id,
        user_id=user["id"],
        target_role=payload.target_role.strip(),
        status_value="active",
        messages=messages,
        proctoring_enabled=payload.proctoring_enabled,
    )
    return InterviewResponse(
        interview_id=payload.interview_id,
        messages=[Message(**message) for message in messages],
        assistant_message=response,
    )


@app.post("/api/interview/feedback")
def generate_feedback(payload: InterviewState, user: sqlite3.Row = Depends(get_current_user)):
    interview = load_interview_for_user(payload.interview_id, user)
    if interview["status"] == "completed" and interview["feedback_report"]:
        return {
            "report": interview["feedback_report"],
            "closing_text": interview["closing_text"] or "Thanks for taking the interview.",
        }

    conversation_text = "\n".join(
        f"{message.role}: {message.content}" for message in payload.messages if message.role != "system"
    )
    proctor_summary = summarize_proctoring(payload.proctor_summary, payload.proctoring_enabled)
    prompt = f"""
Act as a Hiring Manager. Review this interview for a {payload.target_role} role.

TRANSCRIPT:
{conversation_text}

PROCTORING CONTEXT:
{proctor_summary}

Important rules:
- Treat webcam flags as soft signals only.
- Do not accuse the candidate of cheating.
- Mention proctoring observations neutrally in a short section.

Output a Markdown report:
# Interview Performance Report
## Score: [0-100]/100

### Strengths
* [Point 1]
* [Point 2]

### Areas to Improve
* [Point 1]
* [Point 2]

### Proctoring Notes
* [Short neutral note]

### Final Decision
[Hire / No Hire / Next Round]
""".strip()
    report = chat_completion([{"role": "user", "content": prompt}])
    closing_prompt = f"""
Based on this technical interview report, generate a short, warm, and encouraging closing statement (3-4 sentences) to speak to the candidate directly.
Do not read the score or bullet points. Just give a human-like summary of how they did and wish them luck.

REPORT:
{report}
""".strip()
    closing_text = chat_completion([{"role": "user", "content": closing_prompt}])
    full_report = f"{report}\n\n{proctor_summary}"
    completed_at = utc_now_iso()
    save_interview(
        interview_id=payload.interview_id,
        user_id=user["id"],
        target_role=payload.target_role.strip(),
        status_value="completed",
        messages=[message.model_dump() for message in payload.messages],
        proctoring_enabled=payload.proctoring_enabled,
        proctor_summary=payload.proctor_summary,
        report=full_report,
        closing_text=closing_text,
        completed_at=completed_at,
    )
    return {"report": full_report, "closing_text": closing_text}


@app.post("/api/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    target_role: str = Form(default="job interview"),
    prompt_hint: str = Form(default=""),
    user: sqlite3.Row = Depends(get_current_user),
):
    del user
    content = await file.read()
    if not content or len(content) < 4000:
        raise HTTPException(status_code=400, detail="Audio is too short.")

    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp_file.write(content)
        temp_file.close()
        with open(temp_file.name, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                file=(os.path.basename(temp_file.name), audio_file.read()),
                model="whisper-large-v3",
                response_format="text",
                language="en",
                temperature=0,
                prompt=(
                    f"This is a mock interview for a {target_role} role. "
                    "Transcribe carefully, keep technical terms accurate, and do not paraphrase. "
                    f"Recent context: {prompt_hint[:300]}"
                ),
            )
        return {"text": transcript}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc
    finally:
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass


@app.post("/api/proctor/analyze", response_model=ProctorAnalyzeResponse)
async def analyze_frame(
    file: UploadFile = File(...),
    user: sqlite3.Row = Depends(get_current_user),
):
    del user
    if cv2 is None or np is None:
        raise HTTPException(
            status_code=503,
            detail="Proctoring is unavailable because OpenCV dependencies are missing on the backend.",
        )
    content = await file.read()
    np_image = np.frombuffer(content, dtype=np.uint8)
    frame = cv2.imdecode(np_image, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid frame.")

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = get_face_cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(80, 80))
    face_count = len(faces)
    object_info = analyze_objects(frame)
    person_count = int(object_info["persons"])
    phone_count = int(object_info["phones"])
    restricted_objects = list(object_info["restricted_objects"])
    detected_objects = list(object_info["objects"])

    brightness = float(gray.mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    if face_count == 1:
        x, y, w, h = faces[0]
        face_roi = gray[y : y + h, x : x + w]
        if face_roi.size > 0:
            brightness = float(face_roi.mean())
            sharpness = float(cv2.Laplacian(face_roi, cv2.CV_64F).var())

    effective_people = max(face_count, person_count)

    if phone_count > 0:
        status_value = "phone_detected"
        detail = f"Detected {phone_count} mobile phone(s) in the webcam frame."
    elif restricted_objects:
        status_value = "restricted_object"
        detail = "Detected restricted object(s): " + ", ".join(restricted_objects) + "."
    elif effective_people == 0:
        status_value = "no_face"
        detail = "No face detected in the current webcam frame."
    elif effective_people > 1:
        status_value = "multiple_faces"
        detail = f"Detected multiple people in the webcam frame ({effective_people})."
    elif brightness < 24 or sharpness < 8:
        status_value = "low_visibility"
        detail = f"Face visibility is weak right now. Brightness {brightness:.1f}, clarity {sharpness:.1f}."
    else:
        status_value = "clear"
        detail = f"One face verified. Brightness {brightness:.1f}, clarity {sharpness:.1f}."

    return ProctorAnalyzeResponse(
        status=status_value,
        detail=detail,
        faces=effective_people,
        brightness=round(brightness, 1),
        sharpness=round(sharpness, 1),
        frame_hash=hashlib.md5(content).hexdigest(),
        analyzed_at=time.time(),
        phones=phone_count,
        persons=person_count,
        objects=detected_objects[:12],
    )
