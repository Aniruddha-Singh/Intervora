"use client";

import { STATUS_STYLES, formatDate, isFeedbackReport } from "./lib/client";

export function DashboardMetric({ label, value }) {
  return (
    <article className="dashboardMetric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

export function Metric({ label, value }) {
  return (
    <div className="metricCard">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function HistoryCard({ item, admin = false }) {
  return (
    <article className={`historyCard ${admin ? "adminCard" : ""}`}>
      <div className="historyTop">
        <strong>{admin ? item.user_name || item.user_email : item.target_role}</strong>
        <span className={`historyStatus ${item.status === "completed" ? "done" : "live"}`}>{item.status}</span>
      </div>
      <div className="historyMeta">{admin ? item.target_role : formatDate(item.started_at)}</div>
      <div className="historyMeta">
        {admin ? formatDate(item.started_at) : item.score !== null ? `Score ${item.score}/100` : "Score pending"}
      </div>
    </article>
  );
}

export function MonitorPanel({
  roleSet,
  proctoringEnabled,
  videoRef,
  cameraError,
  proctorPaused,
  proctorStatus,
  proctorDetail,
  proctorMetrics,
  proctorStats,
  detectedObjects,
  proctorEvents
}) {
  return (
    <aside className="monitorColumn">
      <section className="monitorCard">
        <div className="sectionBadge">Monitoring</div>
        <h2>Live Monitoring</h2>
        <p>Webcam stays visible here while AI voice and mic continue smoothly in the browser.</p>

        {!roleSet ? (
          <div className="monitorPlaceholder">Camera activates when the interview starts.</div>
        ) : !proctoringEnabled ? (
          <div className="monitorPlaceholder">Proctor Mode is off for this interview.</div>
        ) : (
          <>
            <div className="videoShell">
              <video ref={videoRef} autoPlay playsInline muted className="videoFrame" />
            </div>
            {cameraError && <div className="errorText">{cameraError}</div>}
            {proctorPaused && <div className="pauseText">Monitoring paused while AI voice is speaking.</div>}
            <div className={`statusPill ${STATUS_STYLES[proctorStatus]}`}>{proctorStatus.replace("_", " ")}</div>
            <p className="statusDetail">{proctorDetail}</p>
            <div className="metricsGrid">
              <Metric label="Faces" value={proctorMetrics.faces} />
              <Metric label="Brightness" value={proctorMetrics.brightness} />
              <Metric label="Clarity" value={proctorMetrics.sharpness} />
              <Metric label="Checks" value={Object.values(proctorStats).reduce((sum, count) => sum + count, 0)} />
            </div>
            <div className="eventsBlock">
              <h3>Detected Objects</h3>
              <p>{detectedObjects.length ? detectedObjects.join(", ") : "No tracked objects detected yet."}</p>
            </div>
            <div className="eventsBlock">
              <h3>Recent Events</h3>
              {proctorEvents.length === 0 ? (
                <p>No recent flags.</p>
              ) : (
                proctorEvents
                  .slice()
                  .reverse()
                  .map((event, index) => (
                    <p key={`${event.time}-${index}`}>
                      {event.time} - {event.detail}
                    </p>
                  ))
              )}
            </div>
          </>
        )}
      </section>
    </aside>
  );
}

export function FeedbackReport({ content }) {
  const lines = content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  return (
    <div className="reportBlock">
      {lines.map((line, index) => {
        if (line.startsWith("# Interview Performance Report")) {
          return (
            <div key={index} className="reportTitle">
              Interview Performance Report
            </div>
          );
        }
        if (line.startsWith("## Score:")) {
          return (
            <div key={index} className="reportScore">
              {line.replace("## ", "")}
            </div>
          );
        }
        if (line.startsWith("### Strengths")) {
          return (
            <div key={index} className="reportHeading">
              Strengths
            </div>
          );
        }
        if (line.startsWith("### Areas to Improve")) {
          return (
            <div key={index} className="reportHeading">
              Areas to Improve
            </div>
          );
        }
        if (line.startsWith("### Proctoring Notes")) {
          return (
            <div key={index} className="reportHeading">
              Proctoring Notes
            </div>
          );
        }
        if (line.startsWith("### Final Decision")) {
          return (
            <div key={index} className="reportHeading">
              Final Decision
            </div>
          );
        }
        if (line.startsWith("## Proctoring Summary")) {
          return (
            <div key={index} className="reportHeading">
              Proctoring Summary
            </div>
          );
        }
        if (line.startsWith("* ") || line.startsWith("- ")) {
          return (
            <div key={index} className="reportBullet">
              - {line.slice(2)}
            </div>
          );
        }
        return (
          <div key={index} className="reportText">
            {line}
          </div>
        );
      })}
    </div>
  );
}

export function ChatMessage({ message }) {
  return (
    <article className={`messageCard ${message.role}`}>
      <div className="messageRole">{message.role === "assistant" ? "Interviewer" : "You"}</div>
      <div className="messageBody">
        {message.role === "assistant" && isFeedbackReport(message.content) ? (
          <FeedbackReport content={message.content} />
        ) : (
          message.content
        )}
      </div>
    </article>
  );
}
