"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DashboardMetric, HistoryCard } from "../components";
import {
  authorizedFetch,
  buildEmptyStats,
  clearAuthSession,
  clearInterviewSession,
  fetchCurrentUser,
  fetchDashboardBundle,
  formatDate,
  getStoredToken,
  saveInterviewSession,
  readError
} from "../lib/client";

export default function DashboardPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [appError, setAppError] = useState("");
  const [token, setToken] = useState("");
  const [currentUser, setCurrentUser] = useState(null);
  const [historyItems, setHistoryItems] = useState([]);
  const [adminDashboard, setAdminDashboard] = useState(null);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminItems, setAdminItems] = useState([]);
  const [targetRole, setTargetRole] = useState("");
  const [proctoringEnabled, setProctoringEnabled] = useState(true);

  const totalInterviews = historyItems.length;
  const completedInterviews = historyItems.filter((item) => item.status === "completed").length;
  const activeInterviews = historyItems.filter((item) => item.status === "active").length;
  const scoredInterviews = historyItems.filter((item) => item.score !== null);
  const averageScore = scoredInterviews.length
    ? (scoredInterviews.reduce((sum, item) => sum + item.score, 0) / scoredInterviews.length).toFixed(1)
    : "N/A";

  useEffect(() => {
    initialize();
  }, []);

  async function initialize() {
    const storedToken = getStoredToken();
    if (!storedToken) {
      router.replace("/auth");
      return;
    }

    try {
      const user = await fetchCurrentUser(storedToken);
      const bundle = await fetchDashboardBundle(storedToken, user);
      setToken(storedToken);
      setCurrentUser(user);
      setHistoryItems(bundle.historyItems);
      setAdminDashboard(bundle.adminDashboard);
      setAdminUsers(bundle.adminUsers);
      setAdminItems(bundle.adminItems);
      setReady(true);
    } catch (error) {
      clearAuthSession();
      clearInterviewSession();
      router.replace("/auth");
    }
  }

  async function startInterview() {
    if (!targetRole.trim()) return;
    setAppError("");
    setLoading(true);
    try {
      const response = await authorizedFetch(
        "/api/interview/start",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_role: targetRole.trim(),
            proctoring_enabled: proctoringEnabled
          })
        },
        token
      );

      if (!response.ok) {
        setAppError(await readError(response, "The interview could not be started."));
        return;
      }

      const data = await response.json();
      saveInterviewSession({
        interviewId: data.interview_id,
        targetRole: targetRole.trim(),
        messages: data.messages,
        feedbackShown: false,
        draftAnswer: "",
        proctoringEnabled,
        proctorStatus: "clear",
        proctorDetail: "Exactly one clear face is visible.",
        proctorMetrics: { faces: 0, brightness: 0, sharpness: 0 },
        detectedObjects: [],
        proctorStats: buildEmptyStats(),
        proctorEvents: [],
        cameraError: ""
      });
      router.push("/interview");
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    clearAuthSession();
    clearInterviewSession();
    router.replace("/auth");
  }

  if (!ready || !currentUser) {
    return (
      <main className="routeLoaderShell">
        <section className="routeLoaderCard">
          <div className="sectionBadge">Dashboard</div>
          <h1>Loading your account</h1>
          <p>Preparing history, insights, and admin tools.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="appShell">
      <aside className="shellSidebar">
        <div className="brandBlock">
          <div className="brandMark">IP</div>
          <div>
            <div className="brandName">Interview Pro</div>
            <div className="brandSubtext">Secure AI interview workspace</div>
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
          <h3>Workspace</h3>
          <div className="navCard active">
            <strong>Dashboard</strong>
            <span>Overview, history, and admin insights.</span>
          </div>
          {currentUser.role === "admin" && (
            <button className="navCardButton" onClick={() => router.push("/admin")}>
              Open admin dashboard
            </button>
          )}
          <button className="navCardButton" onClick={() => router.push("/interview")}>
            Resume interview page
          </button>
        </section>

        <section className="sidebarSection">
          <h3>Your History</h3>
          <div className="historyList">
            {historyItems.length === 0 ? (
              <p className="historyEmpty">No interviews yet. Start one to build your report history.</p>
            ) : (
              historyItems.slice(0, 8).map((item) => <HistoryCard key={item.id} item={item} />)
            )}
          </div>
        </section>
      </aside>

      <section className="contentColumn">
        <section className="heroPanel">
          <div className="sectionBadge">Dashboard</div>
          <h1>Launch your next interview with a cleaner workspace</h1>
          <p>
            Everything now lives in dedicated pages, with one visual system across authentication, dashboard,
            live interview, and reporting.
          </p>
        </section>

        <section className="workspaceCard">
          <div className="panelHeader">
            <div>
              <div className="sectionBadge">New Session</div>
              <h2>Start a role-based interview</h2>
            </div>
          </div>

          <label className="fieldLabel">Target role</label>
          <input
            className="roleInput"
            value={targetRole}
            onChange={(event) => setTargetRole(event.target.value)}
            placeholder="e.g. Senior Java Developer, Data Scientist, Product Manager"
          />

          <label className="toggleCard">
            <input
              type="checkbox"
              checked={proctoringEnabled}
              onChange={(event) => setProctoringEnabled(event.target.checked)}
            />
            <span>Enable live proctoring for this session</span>
          </label>

          {appError && <div className="errorBanner">{appError}</div>}

          <div className="ctaRow">
            <button className="primaryButton ctaButton" onClick={startInterview} disabled={loading}>
              {loading ? "Starting..." : "Start Interview"}
            </button>
            <button className="secondaryGhostButton" onClick={() => router.push("/interview")}>
              Open Interview Page
            </button>
          </div>
        </section>

        <section className="workspaceCard">
          <div className="panelHeader">
            <div>
              <div className="sectionBadge">Candidate Dashboard</div>
              <h2>Your interview snapshot</h2>
            </div>
            <p className="panelHeaderText">Track practice progress, report volume, and recent session activity.</p>
          </div>

          <div className="dashboardGrid">
            <DashboardMetric label="Total Interviews" value={totalInterviews} />
            <DashboardMetric label="Completed Reports" value={completedInterviews} />
            <DashboardMetric label="Active Sessions" value={activeInterviews} />
            <DashboardMetric label="Average Score" value={averageScore} />
          </div>

          <div className="dashboardColumns candidateColumns">
            <section className="dashboardCard">
              <h3>Recent Activity</h3>
              <div className="dashboardList">
                {historyItems.length === 0 ? (
                  <p className="historyEmpty">No interview history yet. Start your first mock interview above.</p>
                ) : (
                  historyItems.slice(0, 5).map((item) => (
                    <article key={item.id} className="dashboardListItem">
                      <div className="dashboardListTop">
                        <strong>{item.target_role}</strong>
                        <span className={`historyStatus ${item.status === "completed" ? "done" : "live"}`}>
                          {item.status}
                        </span>
                      </div>
                      <div className="historyMeta">{formatDate(item.started_at)}</div>
                      <div className="historyMeta">
                        {item.score !== null ? `Score ${item.score}/100` : "Feedback still pending"}
                      </div>
                    </article>
                  ))
                )}
              </div>
            </section>

            <section className="dashboardCard">
              <h3>How to use this workspace</h3>
              <div className="dashboardList">
                <article className="dashboardListItem">
                  <div className="dashboardListTop">
                    <strong>1. Pick a target role</strong>
                  </div>
                  <div className="historyMeta">Choose the job role you want to practice before starting a session.</div>
                </article>
                <article className="dashboardListItem">
                  <div className="dashboardListTop">
                    <strong>2. Complete the interview</strong>
                  </div>
                  <div className="historyMeta">Answer by typing or recording your voice while proctoring runs live.</div>
                </article>
                <article className="dashboardListItem">
                  <div className="dashboardListTop">
                    <strong>3. Review your report</strong>
                  </div>
                  <div className="historyMeta">Every completed interview stays attached to your account for later review.</div>
                </article>
              </div>
            </section>
          </div>
        </section>

        {currentUser.role === "admin" && adminDashboard && (
          <section className="workspaceCard">
            <div className="panelHeader">
              <div>
                <div className="sectionBadge">Admin Access</div>
                <h2>Open the admin dashboard</h2>
              </div>
              <p className="panelHeaderText">Use the dedicated admin page for platform analytics, recent users, and flagged sessions.</p>
            </div>

            <div className="dashboardGrid">
              <DashboardMetric label="Total Users" value={adminDashboard.total_users} />
              <DashboardMetric label="Interviews" value={adminDashboard.total_interviews} />
              <DashboardMetric label="Flagged Sessions" value={adminDashboard.flagged_interviews} />
              <DashboardMetric label="Admins" value={adminDashboard.total_admins} />
            </div>

            <div className="ctaRow">
              <button className="primaryButton ctaButton" onClick={() => router.push("/admin")}>
                Open Admin Dashboard
              </button>
            </div>
            <div className="dashboardList compactList">
              {adminUsers[0] && (
                <article className="dashboardListItem">
                  <div className="dashboardListTop">
                    <strong>Latest user</strong>
                    <span className={`historyStatus ${adminUsers[0].role === "admin" ? "done" : "live"}`}>
                      {adminUsers[0].role}
                    </span>
                  </div>
                  <div className="historyMeta">{adminUsers[0].name} • {adminUsers[0].email}</div>
                </article>
              )}
              {adminItems[0] && (
                <article className="dashboardListItem">
                  <div className="dashboardListTop">
                    <strong>Latest interview</strong>
                    <span className={`historyStatus ${adminItems[0].status === "completed" ? "done" : "live"}`}>
                      {adminItems[0].status}
                    </span>
                  </div>
                  <div className="historyMeta">{adminItems[0].target_role} • {adminItems[0].user_name || adminItems[0].user_email}</div>
                </article>
              )}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
