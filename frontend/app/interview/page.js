"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChatMessage, HistoryCard, MonitorPanel } from "../components";
import {
  authorizedFetch,
  buildEmptyStats,
  clearAuthSession,
  clearInterviewSession,
  fetchCurrentUser,
  fetchDashboardBundle,
  getStoredInterviewSession,
  getStoredToken,
  readError,
  saveInterviewSession
} from "../lib/client";

export default function InterviewPage() {
  const router = useRouter();
  const videoRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const speechRef = useRef(null);
  const proctorTimerRef = useRef(null);
  const lastLoggedStatusRef = useRef(null);

  const [ready, setReady] = useState(false);
  const [token, setToken] = useState("");
  const [currentUser, setCurrentUser] = useState(null);
  const [historyItems, setHistoryItems] = useState([]);
  const [appError, setAppError] = useState("");
  const [loading, setLoading] = useState(false);

  const [interviewId, setInterviewId] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [messages, setMessages] = useState([]);
  const [feedbackShown, setFeedbackShown] = useState(false);
  const [draftAnswer, setDraftAnswer] = useState("");
  const [proctoringEnabled, setProctoringEnabled] = useState(true);
  const [proctorPaused, setProctorPaused] = useState(false);
  const [proctorStatus, setProctorStatus] = useState("clear");
  const [proctorDetail, setProctorDetail] = useState("Exactly one clear face is visible.");
  const [proctorMetrics, setProctorMetrics] = useState({ faces: 0, brightness: 0, sharpness: 0 });
  const [detectedObjects, setDetectedObjects] = useState([]);
  const [proctorStats, setProctorStats] = useState(buildEmptyStats());
  const [proctorEvents, setProctorEvents] = useState([]);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [recording, setRecording] = useState(false);

  const roleSet = Boolean(interviewId);
  const chatMessages = useMemo(() => messages.filter((message) => message.role !== "system"), [messages]);

  useEffect(() => {
    initialize();
    return () => {
      stopCamera();
      stopSpeech();
    };
  }, []);

  useEffect(() => {
    if (!videoRef.current || !mediaStreamRef.current) return;
    if (videoRef.current.srcObject !== mediaStreamRef.current) {
      videoRef.current.srcObject = mediaStreamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [roleSet, cameraReady]);

  useEffect(() => {
    if (!roleSet) return;
    if (proctoringEnabled && !cameraReady) {
      startCamera();
    }
    if (!proctoringEnabled && cameraReady) {
      stopCamera();
    }
  }, [roleSet, proctoringEnabled, cameraReady]);

  useEffect(() => {
    if (!roleSet || !proctoringEnabled) {
      stopProctorSampling();
      return;
    }
    if (cameraReady && !proctorPaused) {
      startProctorSampling();
    } else {
      stopProctorSampling();
    }
    return stopProctorSampling;
  }, [roleSet, proctoringEnabled, cameraReady, proctorPaused]);

  useEffect(() => {
    if (!ready) return;
    saveInterviewSession({
      interviewId,
      targetRole,
      messages,
      feedbackShown,
      draftAnswer,
      proctoringEnabled,
      proctorStatus,
      proctorDetail,
      proctorMetrics,
      detectedObjects,
      proctorStats,
      proctorEvents,
      cameraError
    });
  }, [
    ready,
    interviewId,
    targetRole,
    messages,
    feedbackShown,
    draftAnswer,
    proctoringEnabled,
    proctorStatus,
    proctorDetail,
    proctorMetrics,
    detectedObjects,
    proctorStats,
    proctorEvents,
    cameraError
  ]);

  async function initialize() {
    const storedToken = getStoredToken();
    if (!storedToken) {
      router.replace("/auth");
      return;
    }

    try {
      const [user, bundle] = await Promise.all([
        fetchCurrentUser(storedToken),
        fetchDashboardBundle(storedToken, { role: "candidate" })
      ]);
      setToken(storedToken);
      setCurrentUser(user);
      setHistoryItems(bundle.historyItems);

      const storedInterview = getStoredInterviewSession();
      if (storedInterview) {
        hydrateInterview(storedInterview);
      }

      setReady(true);
    } catch (error) {
      clearAuthSession();
      clearInterviewSession();
      router.replace("/auth");
    }
  }

  function hydrateInterview(session) {
    setInterviewId(session.interviewId || "");
    setTargetRole(session.targetRole || "");
    setMessages(session.messages || []);
    setFeedbackShown(Boolean(session.feedbackShown));
    setDraftAnswer(session.draftAnswer || "");
    setProctoringEnabled(session.proctoringEnabled ?? true);
    setProctorStatus(session.proctorStatus || "clear");
    setProctorDetail(session.proctorDetail || "Exactly one clear face is visible.");
    setProctorMetrics(session.proctorMetrics || { faces: 0, brightness: 0, sharpness: 0 });
    setDetectedObjects(session.detectedObjects || []);
    setProctorStats(session.proctorStats || buildEmptyStats());
    setProctorEvents(session.proctorEvents || []);
    setCameraError(session.cameraError || "");
  }

  async function refreshHistory() {
    const bundle = await fetchDashboardBundle(token, currentUser);
    setHistoryItems(bundle.historyItems);
  }

  function handleLogout() {
    stopSpeech();
    stopCamera();
    clearAuthSession();
    clearInterviewSession();
    router.replace("/auth");
  }

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 640 },
          height: { ideal: 360 },
          frameRate: { ideal: 24, max: 30 }
        },
        audio: false
      });
      mediaStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setCameraError("");
      setCameraReady(true);
    } catch (error) {
      setCameraError("Camera access is required for live proctoring.");
      setCameraReady(false);
    }
  }

  function stopCamera() {
    stopProctorSampling();
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setCameraReady(false);
  }

  function startProctorSampling() {
    stopProctorSampling();
    proctorTimerRef.current = window.setInterval(captureAndAnalyzeFrame, 2200);
  }

  function stopProctorSampling() {
    if (proctorTimerRef.current) {
      window.clearInterval(proctorTimerRef.current);
      proctorTimerRef.current = null;
    }
  }

  async function captureAndAnalyzeFrame() {
    if (!videoRef.current || !cameraReady || proctorPaused || !token) return;
    const video = videoRef.current;
    if (!video.videoWidth || !video.videoHeight) return;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.7));
    if (!blob) return;

    const formData = new FormData();
    formData.append("file", blob, "frame.jpg");

    try {
      const response = await authorizedFetch("/api/proctor/analyze", { method: "POST", body: formData }, token);
      if (!response.ok) return;
      const data = await response.json();
      setProctorStatus(data.status);
      setProctorDetail(data.detail);
      setProctorMetrics({
        faces: data.faces,
        brightness: data.brightness,
        sharpness: data.sharpness
      });
      setDetectedObjects(data.objects || []);
      setProctorStats((prev) => ({
        ...prev,
        [data.status]: (prev[data.status] || 0) + 1
      }));

      if (data.status !== "clear" && lastLoggedStatusRef.current !== data.status) {
        const event = {
          time: new Date().toLocaleTimeString(),
          status: data.status,
          detail: data.detail
        };
        setProctorEvents((prev) => [...prev.slice(-4), event]);
        lastLoggedStatusRef.current = data.status;
      }

      if (data.status === "clear") {
        lastLoggedStatusRef.current = null;
      }
    } catch (error) {
      // Keep interview flow smooth during transient proctor sampling issues.
    }
  }

  function speakText(text) {
    if (!("speechSynthesis" in window) || !text) return;
    stopSpeech();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onstart = () => setProctorPaused(true);
    utterance.onend = () => setProctorPaused(false);
    utterance.onerror = () => setProctorPaused(false);
    speechRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeech() {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    speechRef.current = null;
    setProctorPaused(false);
  }

  async function submitTextAnswer(event) {
    event.preventDefault();
    const answer = draftAnswer.trim();
    if (!answer) return;
    setDraftAnswer("");
    await submitUserAnswer(answer);
  }

  async function submitUserAnswer(answerText) {
    const nextMessages = [...messages, { role: "user", content: answerText }];
    setMessages(nextMessages);
    setAppError("");
    setLoading(true);
    try {
      const response = await authorizedFetch(
        "/api/interview/respond",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            interview_id: interviewId,
            target_role: targetRole,
            messages: nextMessages,
            proctoring_enabled: proctoringEnabled
          })
        },
        token
      );

      if (!response.ok) {
        setAppError(await readError(response, "The answer could not be sent."));
        return;
      }

      const data = await response.json();
      setMessages(data.messages);
      speakText(data.assistant_message);
    } finally {
      setLoading(false);
    }
  }

  function toggleRecording() {
    if (proctorPaused) return;
    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
      return;
    }

    navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 16000
        }
      })
      .then((stream) => {
        audioChunksRef.current = [];
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm";
        const recorder = new MediaRecorder(stream, {
          mimeType,
          audioBitsPerSecond: 128000
        });
        mediaRecorderRef.current = recorder;
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) audioChunksRef.current.push(event.data);
        };
        recorder.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
          stream.getTracks().forEach((track) => track.stop());
          if (audioBlob.size < 4000) return;

          const formData = new FormData();
          formData.append("file", audioBlob, "answer.webm");
          formData.append("target_role", targetRole);
          const promptHint =
            messages
              .filter((message) => message.role !== "system")
              .slice(-3)
              .map((message) => `${message.role}: ${message.content}`)
              .join(" | ") || "Mock interview response";
          formData.append("prompt_hint", promptHint);
          setLoading(true);
          try {
            const response = await authorizedFetch("/api/transcribe", { method: "POST", body: formData }, token);
            if (!response.ok) {
              setAppError(await readError(response, "Audio could not be transcribed."));
              return;
            }
            const transcriptData = await response.json();
            if (transcriptData.text) {
              const cleanText = transcriptData.text.toString().trim();
              if (cleanText) {
                setDraftAnswer((prev) => (prev ? `${prev} ${cleanText}` : cleanText));
              }
            }
          } finally {
            setLoading(false);
          }
        };
        recorder.start();
        setRecording(true);
      })
      .catch(() => {
        setAppError("Microphone access is required to record an answer.");
      });
  }

  async function endInterview() {
    if (!interviewId) return;
    setAppError("");
    setLoading(true);
    try {
      const response = await authorizedFetch(
        "/api/interview/feedback",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            interview_id: interviewId,
            target_role: targetRole,
            messages,
            proctoring_enabled: proctoringEnabled,
            proctor_summary: {
              stats: proctorStats,
              events: proctorEvents
            }
          })
        },
        token
      );

      if (!response.ok) {
        setAppError(await readError(response, "Feedback could not be generated."));
        return;
      }

      const data = await response.json();
      const nextMessages = [...messages, { role: "assistant", content: data.report }];
      setMessages(nextMessages);
      setFeedbackShown(true);
      await refreshHistory();
      speakText(data.closing_text);
    } finally {
      setLoading(false);
    }
  }

  function resetInterview() {
    stopSpeech();
    stopCamera();
    clearInterviewSession();
    setInterviewId("");
    setTargetRole("");
    setMessages([]);
    setFeedbackShown(false);
    setDraftAnswer("");
    setProctoringEnabled(true);
    setProctorStatus("clear");
    setProctorDetail("Exactly one clear face is visible.");
    setProctorMetrics({ faces: 0, brightness: 0, sharpness: 0 });
    setDetectedObjects([]);
    setProctorStats(buildEmptyStats());
    setProctorEvents([]);
    setCameraError("");
    setAppError("");
    setRecording(false);
    lastLoggedStatusRef.current = null;
    router.push("/dashboard");
  }

  if (!ready || !currentUser) {
    return (
      <main className="routeLoaderShell">
        <section className="routeLoaderCard">
          <div className="sectionBadge">Interview</div>
          <h1>Opening your live session</h1>
          <p>Restoring account access, messages, and proctoring state.</p>
        </section>
      </main>
    );
  }

  if (!roleSet) {
    return (
      <main className="routeLoaderShell">
        <section className="routeLoaderCard">
          <div className="sectionBadge">No Active Session</div>
          <h1>Start from the dashboard</h1>
          <p>Your interview page is ready, but there is no active session to restore yet.</p>
          <button className="primaryButton routeLoaderButton" onClick={() => router.push("/dashboard")}>
            Go To Dashboard
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="pageShell">
      <aside className="sidebar">
        <div className="brandBlock brandBlockCompact">
          <div className="brandMark">IP</div>
          <div>
            <div className="brandName">Interview Pro</div>
            <div className="brandSubtext">Live interview workspace</div>
          </div>
        </div>

        <div className="userCard">
          <div className="userRoleTag">{currentUser.role}</div>
          <h2>{currentUser.name}</h2>
          <p>{currentUser.email}</p>
          <button className="ghostButton" onClick={handleLogout}>
            Log Out
          </button>
        </div>

        <section className="sidebarSection">
          <h3>Navigation</h3>
          <button className="navCardButton" onClick={() => router.push("/dashboard")}>
            Back to dashboard
          </button>
        </section>

        <section className="sidebarSection">
          <h3>Session Controls</h3>
          <label className="checkboxRow">
            <input
              type="checkbox"
              checked={proctoringEnabled}
              onChange={(event) => setProctoringEnabled(event.target.checked)}
            />
            <span>Enable Proctor Mode</span>
          </label>

          <div className="roleCard">
            Interviewing for: <strong>{targetRole}</strong>
          </div>
          <div className="flagsText">
            Proctor flags recorded:{" "}
            {proctorStats.no_face +
              proctorStats.multiple_faces +
              proctorStats.low_visibility +
              proctorStats.phone_detected +
              proctorStats.restricted_object}
          </div>
          <button className="primaryButton" onClick={endInterview} disabled={loading || feedbackShown}>
            End Interview &amp; Get Feedback
          </button>
          <button className="secondaryButton" onClick={resetInterview}>
            Close Session
          </button>
        </section>

        <section className="sidebarSection">
          <h3>Recent Reports</h3>
          <div className="historyList">
            {historyItems.length === 0 ? (
              <p className="historyEmpty">No interviews yet. Complete one to store your report.</p>
            ) : (
              historyItems.slice(0, 8).map((item) => <HistoryCard key={item.id} item={item} />)
            )}
          </div>
        </section>
      </aside>

      <section className="mainColumn">
        <header className="pageHeader pageHeaderWide">
          <div className="sectionBadge">Protected Interview Session</div>
          <h1>Mock Interview: {targetRole}</h1>
          <p>
            Focus on the conversation while the browser manages your microphone, AI voice, and webcam monitoring in
            the background.
          </p>
        </header>

        {appError && <div className="errorBanner">{appError}</div>}

        <div className="chatStack">
          {chatMessages.map((message, index) => (
            <ChatMessage key={`${message.role}-${index}`} message={message} />
          ))}
        </div>

        {!feedbackShown && (
          <form className="answerPanel" onSubmit={submitTextAnswer}>
            <textarea
              name="answer"
              placeholder="Type your answer here, or use the mic and review the transcript before sending..."
              rows={4}
              value={draftAnswer}
              onChange={(event) => setDraftAnswer(event.target.value)}
            />
            <div className="inputHint">
              Mic recordings fill the answer box first so you can correct any transcription mistakes before sending.
            </div>
            <div className="answerActions">
              <button type="submit" className="primaryButton" disabled={loading}>
                Send Answer
              </button>
              <button
                type="button"
                className="micButton"
                onClick={toggleRecording}
                disabled={loading || proctorPaused}
              >
                {recording ? "Stop Recording" : proctorPaused ? "Wait For AI Voice" : "Record Answer"}
              </button>
            </div>
          </form>
        )}

        {loading && <div className="loadingBar">Working on it...</div>}
      </section>

      <MonitorPanel
        roleSet={roleSet}
        proctoringEnabled={proctoringEnabled}
        videoRef={videoRef}
        cameraError={cameraError}
        proctorPaused={proctorPaused}
        proctorStatus={proctorStatus}
        proctorDetail={proctorDetail}
        proctorMetrics={proctorMetrics}
        proctorStats={proctorStats}
        detectedObjects={detectedObjects}
        proctorEvents={proctorEvents}
      />
    </main>
  );
}
