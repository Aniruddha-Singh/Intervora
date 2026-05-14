"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DashboardMetric } from "../components";
import {
  clearAuthSession,
  clearInterviewSession,
  fetchCurrentUser,
  fetchDashboardBundle,
  formatDate,
  getStoredToken
} from "../lib/client";

export default function AdminPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [adminDashboard, setAdminDashboard] = useState(null);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminItems, setAdminItems] = useState([]);

  useEffect(() => {
    initialize();
  }, []);

  async function initialize() {
    const token = getStoredToken();
    if (!token) {
      router.replace("/auth");
      return;
    }

    try {
      const user = await fetchCurrentUser(token);
      if (user.role !== "admin") {
        router.replace("/dashboard");
        return;
      }

      const bundle = await fetchDashboardBundle(token, user);
      setCurrentUser(user);
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

  function handleLogout() {
    clearAuthSession();
    clearInterviewSession();
    router.replace("/auth");
  }

  if (!ready || !currentUser || !adminDashboard) {
    return (
      <main className="routeLoaderShell">
        <section className="routeLoaderCard">
          <div className="sectionBadge">Admin</div>
          <h1>Opening the admin dashboard</h1>
          <p>Loading platform metrics, recent users, and interview activity.</p>
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
            <div className="brandSubtext">Administrative controls</div>
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
          <button className="navCardButton" onClick={() => router.push("/dashboard")}>
            Back to dashboard
          </button>
          <button className="navCardButton" onClick={() => router.push("/interview")}>
            Open interview page
          </button>
        </section>
      </aside>

      <section className="contentColumn">
        <section className="heroPanel">
          <div className="sectionBadge">Admin Dashboard</div>
          <h1>Platform monitoring and candidate activity</h1>
          <p>Review user growth, interview throughput, scores, and suspicious proctoring patterns from one place.</p>
        </section>

        <section className="workspaceCard">
          <div className="panelHeader">
            <div>
              <div className="sectionBadge">Overview</div>
              <h2>Live platform metrics</h2>
            </div>
          </div>

          <div className="dashboardGrid">
            <DashboardMetric label="Total Users" value={adminDashboard.total_users} />
            <DashboardMetric label="Admins" value={adminDashboard.total_admins} />
            <DashboardMetric label="Candidates" value={adminDashboard.total_candidates} />
            <DashboardMetric label="Interviews" value={adminDashboard.total_interviews} />
            <DashboardMetric label="Completed" value={adminDashboard.completed_interviews} />
            <DashboardMetric label="Active" value={adminDashboard.active_interviews} />
            <DashboardMetric
              label="Average Score"
              value={adminDashboard.average_score !== null ? adminDashboard.average_score : "N/A"}
            />
            <DashboardMetric label="Flagged Sessions" value={adminDashboard.flagged_interviews} />
          </div>
        </section>

        <section className="workspaceCard">
          <div className="panelHeader">
            <div>
              <div className="sectionBadge">Recent Users</div>
              <h2>Newest account activity</h2>
            </div>
          </div>

          <div className="dashboardColumns">
            <section className="dashboardCard">
              <h3>Recent Users</h3>
              <div className="dashboardList">
                {adminUsers.length === 0 ? (
                  <p className="historyEmpty">No users available yet.</p>
                ) : (
                  adminUsers.map((user) => (
                    <article key={user.id} className="dashboardListItem">
                      <div className="dashboardListTop">
                        <strong>{user.name}</strong>
                        <span className={`historyStatus ${user.role === "admin" ? "done" : "live"}`}>
                          {user.role}
                        </span>
                      </div>
                      <div className="historyMeta">{user.email}</div>
                      <div className="historyMeta">
                        Joined {formatDate(user.created_at)} • {user.interview_count} interviews
                      </div>
                    </article>
                  ))
                )}
              </div>
            </section>

            <section className="dashboardCard">
              <h3>Recent Interviews</h3>
              <div className="dashboardList">
                {adminItems.length === 0 ? (
                  <p className="historyEmpty">No interview activity recorded yet.</p>
                ) : (
                  adminItems.map((item) => (
                    <article key={item.id} className="dashboardListItem">
                      <div className="dashboardListTop">
                        <strong>{item.target_role}</strong>
                        <span className={`historyStatus ${item.status === "completed" ? "done" : "live"}`}>
                          {item.status}
                        </span>
                      </div>
                      <div className="historyMeta">{item.user_name || item.user_email}</div>
                      <div className="historyMeta">
                        {formatDate(item.started_at)}
                        {item.score !== null ? ` • Score ${item.score}/100` : ""}
                      </div>
                    </article>
                  ))
                )}
              </div>
            </section>
          </div>
        </section>
      </section>
    </main>
  );
}
