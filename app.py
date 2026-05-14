import streamlit as st
import os
from openai import OpenAI
from dotenv import load_dotenv
from audio_recorder_streamlit import audio_recorder
from gtts import gTTS
import tempfile
import base64
import time
import re
import hashlib
from datetime import datetime

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

try:
    from camera_input_live import camera_input_live
except ImportError:
    camera_input_live = None

PROCTOR_ANALYSIS_INTERVAL = 1.5
PROCTOR_MIN_STREAK = 2
AUDIO_PAUSE_BUFFER_SECONDS = 1.0

# --- 1. CONFIGURATION ---
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    st.error("API Key not found! Please check your .env file.")
    st.stop()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=groq_api_key,
)

st.set_page_config(page_title="Interview Pro", page_icon="🎙️", layout="wide")

# --- 2. CSS STYLING ---
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }

    .stChatMessage {
        background-color: #1A1C23;
        border: 1px solid #2D2F36;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 16px;
    }
    .stChatMessage p, .stChatMessage li, .stChatMessage h1, .stChatMessage h2, .stChatMessage h3 {
        color: #FAFAFA !important;
    }

    .stChatInputInput {
        background-color: #262730 !important;
        color: #FAFAFA !important;
        border: 1px solid #444 !important;
    }
    div[data-testid="stChatInput"] {
        background-color: #0E1117 !important;
    }

    .stButton button {
        background-color: #4CAF50;
        color: white;
        border: none;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton button:hover {
        background-color: #45a049;
        color: white;
        transform: scale(1.02);
    }

    .answer-tools {
        margin-top: 12px;
        padding: 14px 16px;
        border-radius: 14px;
        background: rgba(26, 28, 35, 0.78);
        border: 1px solid rgba(255,255,255,0.08);
    }

    .mic-inline {
        display: flex;
        justify-content: flex-start;
        align-items: center;
        min-height: 56px;
    }

    .proctor-card {
        background: linear-gradient(180deg, rgba(25, 31, 42, 0.96), rgba(14, 17, 23, 0.98));
        border: 1px solid #2D2F36;
        border-radius: 18px;
        padding: 16px;
        margin-bottom: 16px;
    }

    .proctor-status {
        border-radius: 999px;
        display: inline-block;
        font-size: 0.85rem;
        font-weight: 700;
        margin-top: 8px;
        padding: 6px 12px;
    }

    .status-clear {
        background-color: rgba(76, 175, 80, 0.16);
        color: #9BE7A0;
        border: 1px solid rgba(76, 175, 80, 0.3);
    }

    .status-alert {
        background-color: rgba(255, 152, 0, 0.16);
        color: #FFD08A;
        border: 1px solid rgba(255, 152, 0, 0.35);
    }

    .status-danger {
        background-color: rgba(255, 82, 82, 0.16);
        color: #FF9E9E;
        border: 1px solid rgba(255, 82, 82, 0.35);
    }

    .main .block-container {
        padding-bottom: 60px;
    }

    .stDeployButton {display:none;}
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 3. STATE MANAGEMENT ---
DEFAULT_STATE = {
    "messages": [],
    "role_set": False,
    "target_role": "",
    "feedback_shown": False,
    "last_audio": None,
    "check_audio": False,
    "last_feedback_audio": None,
    "proctoring_enabled": True,
    "proctor_events": [],
    "proctor_stats": {"clear": 0, "no_face": 0, "multiple_faces": 0, "low_visibility": 0},
    "proctor_last_status": "clear",
    "proctor_last_metrics": {"brightness": 0.0, "sharpness": 0.0, "faces": 0},
    "last_proctor_frame_hash": None,
    "last_flagged_status": None,
    "last_flagged_at": 0.0,
    "last_proctor_analysis_at": 0.0,
    "proctor_candidate_status": "clear",
    "proctor_candidate_streak": 0,
    "interview_started_at": None,
    "proctor_pause_until": 0.0,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        if isinstance(value, dict):
            st.session_state[key] = value.copy()
        elif isinstance(value, list):
            st.session_state[key] = value[:]
        else:
            st.session_state[key] = value


def reset_interview_state():
    st.session_state.messages = []
    st.session_state.role_set = False
    st.session_state.target_role = ""
    st.session_state.feedback_shown = False
    st.session_state.last_audio = None
    st.session_state.check_audio = False
    st.session_state.last_feedback_audio = None
    st.session_state.proctor_events = []
    st.session_state.proctor_stats = {"clear": 0, "no_face": 0, "multiple_faces": 0, "low_visibility": 0}
    st.session_state.proctor_last_status = "clear"
    st.session_state.proctor_last_metrics = {"brightness": 0.0, "sharpness": 0.0, "faces": 0}
    st.session_state.last_proctor_frame_hash = None
    st.session_state.last_flagged_status = None
    st.session_state.last_flagged_at = 0.0
    st.session_state.last_proctor_analysis_at = 0.0
    st.session_state.proctor_candidate_status = "clear"
    st.session_state.proctor_candidate_streak = 0
    st.session_state.interview_started_at = None
    st.session_state.proctor_pause_until = 0.0


# --- REQUIRED for Chrome Autoplay ---
def unlock_audio_autoplay():
    silent_audio = """
        <audio autoplay style="display:none;">
            <source src="data:audio/mp3;base64,//uQxAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAACcQCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA">
            </audio>
    """
    st.markdown(silent_audio, unsafe_allow_html=True)


def estimate_tts_duration_seconds(text):
    words = max(1, len(text.split()))
    return max(2.0, words / 2.8)


def pause_proctoring_for_tts(text):
    duration = estimate_tts_duration_seconds(text) + AUDIO_PAUSE_BUFFER_SECONDS
    st.session_state.proctor_pause_until = time.time() + duration


# --- 4. FUNCTIONS ---
def autoplay_audio(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    md = f"""
        <audio autoplay style="display:none;">
        <source src="data:audio/mp3;base64,{b64}" type="audio/mpeg">
        </audio>
        """
    st.markdown(md, unsafe_allow_html=True)


def text_to_speech(text):
    try:
        tts = gTTS(text=text, lang="en")
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts.save(temp_file.name)
        temp_file.close()
        return temp_file.name
    except Exception:
        return None


def clean_response_text(text):
    text = re.sub(r"^\d+[\.\)]\s*", "", text)
    text = re.sub(r"\(Note:.*?\)", "", text, flags=re.IGNORECASE)
    return text


def transcribe_audio(audio_bytes):
    if not audio_bytes or len(audio_bytes) < 4000:
        return None

    try:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.write(audio_bytes)
        temp_file.close()
        with open(temp_file.name, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(temp_file.name, file.read()),
                model="whisper-large-v3",
                response_format="text",
            )
        os.unlink(temp_file.name)
        return transcription
    except Exception as e:
        if "too short" in str(e):
            return None
        st.error(f"Transcription error: {str(e)}")
        return None


def get_face_cascade():
    if cv2 is None:
        return None
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def add_proctor_event(status, detail):
    event = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "status": status,
        "detail": detail,
    }
    st.session_state.proctor_events.append(event)
    st.session_state.proctor_events = st.session_state.proctor_events[-8:]


STATUS_CONFIG = {
    "clear": {"label": "Clear", "class_name": "status-clear", "detail": "Exactly one clear face is visible."},
    "low_visibility": {"label": "Low visibility", "class_name": "status-alert", "detail": "The detected face is too dim or soft to verify confidently."},
    "no_face": {"label": "No face detected", "class_name": "status-danger", "detail": "The candidate may have moved off camera."},
    "multiple_faces": {"label": "Multiple faces", "class_name": "status-danger", "detail": "More than one face is visible in the frame."},
}


def compute_frame_status(image_file):
    if not image_file or cv2 is None or np is None:
        return None, None

    frame_bytes = image_file.getvalue()
    frame_hash = hashlib.md5(frame_bytes).hexdigest()
    if frame_hash == st.session_state.last_proctor_frame_hash:
        return st.session_state.proctor_last_status, st.session_state.proctor_last_metrics

    np_image = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame = cv2.imdecode(np_image, cv2.IMREAD_COLOR)
    if frame is None:
        return st.session_state.proctor_last_status, st.session_state.proctor_last_metrics

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    face_cascade = get_face_cascade()
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(80, 80)) if face_cascade else []
    face_count = len(faces)

    brightness = float(gray.mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    if face_count == 1:
        x, y, w, h = faces[0]
        face_roi = gray[y : y + h, x : x + w]
        if face_roi.size > 0:
            brightness = float(face_roi.mean())
            sharpness = float(cv2.Laplacian(face_roi, cv2.CV_64F).var())

    metrics = {
        "brightness": round(brightness, 1),
        "sharpness": round(sharpness, 1),
        "faces": face_count,
        "frame_hash": frame_hash,
    }

    if face_count == 0:
        status = "no_face"
        detail = "No face detected in the current webcam frame."
    elif face_count > 1:
        status = "multiple_faces"
        detail = f"Detected {face_count} faces in the current webcam frame."
    elif brightness < 24 or sharpness < 8:
        status = "low_visibility"
        detail = f"Face visibility is weak right now. Brightness {brightness:.1f}, clarity {sharpness:.1f}."
    else:
        status = "clear"
        detail = f"One face verified. Brightness {brightness:.1f}, clarity {sharpness:.1f}."

    metrics["detail"] = detail
    return status, metrics


def analyze_proctor_frame(image_file):
    if not image_file or cv2 is None or np is None:
        return st.session_state.proctor_last_status

    if time.time() < st.session_state.proctor_pause_until:
        return st.session_state.proctor_last_status

    now_ts = time.time()
    if now_ts - st.session_state.last_proctor_analysis_at < PROCTOR_ANALYSIS_INTERVAL:
        return st.session_state.proctor_last_status

    status, metrics = compute_frame_status(image_file)
    if not status or not metrics:
        return st.session_state.proctor_last_status

    st.session_state.last_proctor_analysis_at = now_ts
    st.session_state.last_proctor_frame_hash = metrics.pop("frame_hash", None)

    candidate_status = st.session_state.proctor_candidate_status
    candidate_streak = st.session_state.proctor_candidate_streak

    if status == candidate_status:
        candidate_streak += 1
    else:
        candidate_status = status
        candidate_streak = 1

    st.session_state.proctor_candidate_status = candidate_status
    st.session_state.proctor_candidate_streak = candidate_streak

    final_status = st.session_state.proctor_last_status
    if status == "clear":
        final_status = "clear"
    elif candidate_streak >= PROCTOR_MIN_STREAK:
        final_status = status

    st.session_state.proctor_last_status = final_status
    st.session_state.proctor_last_metrics = {
        "brightness": metrics.get("brightness", 0.0),
        "sharpness": metrics.get("sharpness", 0.0),
        "faces": metrics.get("faces", 0),
    }
    st.session_state.proctor_stats[final_status] = st.session_state.proctor_stats.get(final_status, 0) + 1

    detail = metrics.get("detail", STATUS_CONFIG[final_status]["detail"])
    flagged = final_status != "clear"
    should_log = flagged and (
        st.session_state.last_flagged_status != final_status or now_ts - st.session_state.last_flagged_at > 10
    )
    if should_log:
        add_proctor_event(final_status, detail)
        st.session_state.last_flagged_status = final_status
        st.session_state.last_flagged_at = now_ts
    elif final_status == "clear":
        st.session_state.last_flagged_status = None

    return final_status


def build_proctoring_summary():
    if not st.session_state.proctoring_enabled:
        return "Proctor mode was disabled for this interview."

    stats = st.session_state.proctor_stats
    total_checks = sum(stats.values())
    suspicious_checks = stats.get("no_face", 0) + stats.get("multiple_faces", 0) + stats.get("low_visibility", 0)

    if total_checks == 0:
        return "Proctor mode was enabled, but no webcam frames were captured."

    summary_lines = [
        "## Proctoring Summary",
        f"- Webcam checks processed: {total_checks}",
        f"- Clear frames: {stats.get('clear', 0)}",
        f"- No-face flags: {stats.get('no_face', 0)}",
        f"- Multiple-face flags: {stats.get('multiple_faces', 0)}",
        f"- Low-visibility flags: {stats.get('low_visibility', 0)}",
    ]

    if suspicious_checks == 0:
        summary_lines.append("- Overall result: No suspicious webcam events were detected.")
    else:
        summary_lines.append("- Overall result: Review flagged moments before making any decision.")

    if st.session_state.proctor_events:
        summary_lines.append("- Recent flagged events:")
        for event in st.session_state.proctor_events[-5:]:
            summary_lines.append(f"  - {event['time']}: {event['detail']}")

    return "\n".join(summary_lines)


def generate_feedback():
    conversation_text = "\n".join(
        [f"{m['role']}: {m['content']}" for m in st.session_state.messages if m["role"] != "system"]
    )
    proctor_summary = build_proctoring_summary()
    prompt = f"""
    Act as a Hiring Manager. Review this interview for a {st.session_state.target_role} role.

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
    """
    report = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content
    return f"{report}\n\n{proctor_summary}"


def generate_closing_audio_text(report_text):
    prompt = f"""
    Based on this technical interview report, generate a short, warm, and encouraging closing statement (3-4 sentences) to speak to the candidate directly.
    Do not read the score or bullet points. Just give a human-like summary of how they did and wish them luck.

    REPORT:
    {report_text}
    """
    return client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content


def play_response_audio(text):
    pause_proctoring_for_tts(text)
    audio_file = text_to_speech(text)
    if audio_file:
        unlock_audio_autoplay()
        autoplay_audio(audio_file)
        try:
            os.remove(audio_file)
        except OSError:
            pass


def render_proctor_panel():
    st.markdown('<div class="proctor-card">', unsafe_allow_html=True)
    st.subheader("Live Monitoring")
    st.caption("Video monitoring pauses briefly while the AI interviewer is speaking so the browser can play audio reliably.")

    if not st.session_state.proctoring_enabled:
        st.info("Proctor Mode is off for this interview.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if camera_input_live is None:
        st.warning("Install `streamlit-camera-input-live` to enable live webcam checks.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if cv2 is None or np is None:
        st.warning("Install `opencv-python-headless` and `numpy` to enable webcam analysis.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    proctor_paused = time.time() < st.session_state.proctor_pause_until
    if proctor_paused:
        remaining = max(0.0, st.session_state.proctor_pause_until - time.time())
        st.info(f"Proctoring paused while AI audio is playing. Resumes in about {remaining:.1f}s.")
    else:
        image = camera_input_live(key="proctor_live")
        status = analyze_proctor_frame(image) if image else st.session_state.proctor_last_status
        config = STATUS_CONFIG.get(status or "clear", STATUS_CONFIG["clear"])
        st.markdown(
            f'<div class="proctor-status {config["class_name"]}">{config["label"]}</div>',
            unsafe_allow_html=True,
        )
        st.write(config["detail"])

    metrics = st.session_state.proctor_last_metrics
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    stat_col1.metric("Faces", metrics.get("faces", 0))
    stat_col2.metric("Brightness", metrics.get("brightness", 0.0))
    stat_col3.metric("Clarity", metrics.get("sharpness", 0.0))

    stats = st.session_state.proctor_stats
    total_checks = sum(stats.values())
    suspicious_checks = stats.get("no_face", 0) + stats.get("multiple_faces", 0) + stats.get("low_visibility", 0)
    summary_col1, summary_col2 = st.columns(2)
    summary_col1.metric("Webcam checks", total_checks)
    summary_col2.metric("Flagged events", suspicious_checks)

    if st.session_state.proctor_events:
        st.write("Recent events")
        for event in reversed(st.session_state.proctor_events[-3:]):
            st.caption(f"{event['time']} - {event['detail']}")

    st.markdown("</div>", unsafe_allow_html=True)


# --- 5. APP LAYOUT ---
with st.sidebar:
    st.title("Controls")
    st.session_state.proctoring_enabled = st.checkbox(
        "Enable Proctor Mode",
        value=st.session_state.proctoring_enabled,
        help="Uses the webcam to flag no-face, multiple-face, and low-visibility moments during the interview.",
    )

    if st.session_state.role_set:
        st.info(f"Interviewing for: **{st.session_state.target_role}**")
        if st.session_state.proctoring_enabled:
            flagged = (
                st.session_state.proctor_stats.get("no_face", 0)
                + st.session_state.proctor_stats.get("multiple_faces", 0)
                + st.session_state.proctor_stats.get("low_visibility", 0)
            )
            st.caption(f"Proctor flags recorded: {flagged}")

        if st.button("End Interview & Get Feedback", type="primary", use_container_width=True):
            with st.spinner("Generating comprehensive feedback report..."):
                feedback = generate_feedback()
                st.session_state.messages.append({"role": "assistant", "content": feedback})
                st.session_state.feedback_shown = True
                spoken_summary = generate_closing_audio_text(feedback)
                st.session_state.last_feedback_audio = spoken_summary
            st.rerun()

        if st.button("Start New Interview", use_container_width=True):
            reset_interview_state()
            st.rerun()


if not st.session_state.role_set:
    st.markdown(
        "<div style='text-align: center; padding-top: 50px;'><h1 style='color: #FAFAFA;'>AI Interview Coach</h1></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='text-align: center;'><h3 style='color: #FAFAFA;'>Practice for your dream job with AI-powered mock interviews</h3></div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        target_role = st.text_input(
            "Role Name",
            placeholder="e.g. Senior Java Developer, Data Scientist, Product Manager",
            label_visibility="collapsed",
        )
        st.caption("Optional: turn on Proctor Mode in the sidebar before you begin if you want webcam-based monitoring.")
        if st.button("Start Interview", use_container_width=True, type="primary"):
            if target_role:
                st.session_state.target_role = target_role
                st.session_state.interview_started_at = time.time()

                sys_prompt = f"""
                You are a professional interviewer for a {target_role} role.

                INSTRUCTIONS:
                1. Start immediately by welcoming the candidate and asking for their introduction.
                2. Do not say 'Note:', 'I will follow...', or 'Okay'. Just speak.
                3. Ask relevant follow-up questions.
                4. Refuse off-topic requests firmly but politely.
                5. Keep responses concise, maximum 2 sentences.
                6. If it is a developer role, ask coding questions only when useful.
                """
                st.session_state.messages = [{"role": "system", "content": sys_prompt}]

                with st.spinner("Setting up your personalized interview session..."):
                    greeting = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": "Start the interview now. Output only the spoken greeting."},
                        ],
                    ).choices[0].message.content

                    greeting = clean_response_text(greeting)
                    st.session_state.messages.append({"role": "assistant", "content": greeting})
                    st.session_state.role_set = True
                    st.session_state.check_audio = True
                    st.rerun()
            else:
                st.warning("Please enter a role to begin the interview")
else:
    if st.session_state.check_audio:
        greeting_text = st.session_state.messages[-1]["content"]
        play_response_audio(greeting_text)
        st.session_state.check_audio = False

    if st.session_state.last_feedback_audio:
        play_response_audio(st.session_state.last_feedback_audio)
        st.session_state.last_feedback_audio = None

    left_col, right_col = st.columns([1.7, 1.0])

    with left_col:
        st.title(f"Mock Interview: {st.session_state.target_role}")
        if st.session_state.proctoring_enabled:
            st.caption("Type your answer, or use the mic directly below the answer box. Webcam monitoring pauses briefly while AI audio is speaking.")
        else:
            st.caption("Type your answer, or use the mic directly below the answer box. Pausing for 5 seconds will auto-submit.")

        for message in st.session_state.messages:
            if message["role"] != "system":
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        text_input = st.chat_input("Type your answer here...")
        user_msg = text_input if text_input else None

        if user_msg:
            st.session_state.messages.append({"role": "user", "content": user_msg})
            st.session_state.last_audio = None
            st.rerun()

        st.markdown('<div class="answer-tools">', unsafe_allow_html=True)
        st.caption("Record your answer")
        st.markdown('<div class="mic-inline">', unsafe_allow_html=True)
        audio_bytes = None
        if st.session_state.role_set and not st.session_state.feedback_shown:
            audio_bytes = audio_recorder(
                text="",
                recording_color="#ff4b4b",
                neutral_color="#4CAF50",
                icon_name="microphone",
                icon_size="2x",
                key="inline_mic",
                pause_threshold=5.0,
            )
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if audio_bytes and audio_bytes != st.session_state.last_audio:
            st.session_state.last_audio = audio_bytes
            with st.spinner("Transcribing your response..."):
                user_msg = transcribe_audio(audio_bytes)
                if user_msg:
                    st.session_state.messages.append({"role": "user", "content": user_msg})
                    st.rerun()

        if st.session_state.messages and st.session_state.messages[-1]["role"] == "user" and not st.session_state.feedback_shown:
            if len(st.session_state.messages) == 36:
                st.session_state.messages.append(
                    {"role": "system", "content": "You have gathered sufficient data. Ask 1-2 final questions and then conclude the interview."}
                )

            if len(st.session_state.messages) > 50:
                with st.chat_message("assistant"):
                    st.markdown("**Interview complete. Generating feedback...**")
                with st.spinner("Generating report..."):
                    feedback = generate_feedback()
                    st.session_state.messages.append({"role": "assistant", "content": feedback})
                    st.session_state.feedback_shown = True
                    spoken_summary = generate_closing_audio_text(feedback)
                    st.session_state.last_feedback_audio = spoken_summary
                st.rerun()
            else:
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        response = client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=st.session_state.messages,
                        ).choices[0].message.content

                        response = clean_response_text(response)
                        st.markdown(response)

                st.session_state.messages.append({"role": "assistant", "content": response})
                play_response_audio(response)

    with right_col:
        render_proctor_panel()
