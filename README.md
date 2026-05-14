# Interview Pro

## Overview
Interview Pro is an AI mock interview application with:
- role-based interview prompts
- typed and spoken candidate answers
- live webcam monitoring for soft proctoring
- final interview scoring and written feedback

This project now contains two versions:
- `app.py`: the original Streamlit version
- `frontend/` + `backend/`: the new lighter web architecture using `Next.js` and `FastAPI`

The new architecture is the recommended path because browser-native media handling is much smoother for webcam, mic, and AI voice playback.

## Recommended Architecture
- Frontend: `Next.js`
- Backend: `FastAPI`
- LLM: Groq via OpenAI-compatible API
- Speech-to-text: Whisper Large v3
- AI voice playback: browser `speechSynthesis`
- Proctoring: live webcam preview in browser plus sampled frame analysis through FastAPI and OpenCV
- Authentication: token-based login with role-aware access
- Storage: SQLite for users, interview history, and scores

## New Project Structure
- `frontend/`: browser UI for the interview, mic, webcam, and AI voice
- `backend/`: FastAPI endpoints for interview logic, transcription, feedback, and proctoring analysis
- `app.py`: old Streamlit version kept for reference

## Backend Setup
From the project root:

```powershell
cd C:\Users\91727\Desktop\finalpro
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Make sure your `.env` file contains:

```text
GROQ_API_KEY=gsk_your_key_here
AUTH_SECRET_KEY=change_this_for_production
ADMIN_EMAILS=admin@example.com
```

Run the backend:

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## Frontend Setup
The frontend lives in `frontend/`.

Create a local env file from the example:

```powershell
copy frontend\.env.local.example frontend\.env.local
```

It should contain:

```text
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

Then install frontend packages and start Next.js:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## Current Machine Note
Python is available on this machine, but `node` / `npm` were not usable during the migration session, so the frontend code was scaffolded but not executed here. Once Node.js is available normally on your machine, the frontend should be ready to install and run.

## How The New Version Works
1. Enter a target role and start the interview.
2. The backend creates the interviewer system prompt and first greeting.
3. The browser plays AI voice using native speech synthesis.
4. The candidate can type answers or record answers with the browser mic.
5. Audio is sent to FastAPI for Whisper transcription.
6. Webcam video stays local in the browser and sampled frames are sent to the backend every few seconds for analysis.
7. Final feedback includes neutral proctoring notes.
8. Each authenticated user gets saved interview history and stored scores.

## Authentication Features
- Candidate and admin accounts can sign up and log in from the frontend
- Protected API routes now require a bearer token
- Interview sessions are stored per user in SQLite
- Admin users can review recent platform interview activity
- The first registered user can become an admin, or you can allow admin signups through `ADMIN_EMAILS`

## Why This Version Is Faster
- no Streamlit full-page reruns
- browser-native webcam handling
- browser-native mic recording
- browser-native speech playback
- lightweight sampled proctoring instead of heavy continuous UI refreshes

## Existing Streamlit Version
If you still want to run the old version:

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Main Files
- [backend/main.py](C:/Users/91727/Desktop/finalpro/backend/main.py): FastAPI API for interview logic and proctoring
- [frontend/app/page.js](C:/Users/91727/Desktop/finalpro/frontend/app/page.js): main Next.js interview page
- [frontend/app/globals.css](C:/Users/91727/Desktop/finalpro/frontend/app/globals.css): UI styling
- [frontend/package.json](C:/Users/91727/Desktop/finalpro/frontend/package.json): frontend dependencies and scripts
