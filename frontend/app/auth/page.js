"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  API_BASE,
  buildInitialAuthForm,
  clearAuthSession,
  getStoredToken,
  readError,
  saveAuthSession
} from "../lib/client";

export default function AuthPage() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState("login");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authForm, setAuthForm] = useState(buildInitialAuthForm());

  useEffect(() => {
    if (getStoredToken()) {
      router.replace("/dashboard");
    } else {
      clearAuthSession();
    }
  }, [router]);

  async function handleAuthSubmit(event) {
    event.preventDefault();
    setAuthError("");
    setAuthLoading(true);

    const payload =
      authMode === "signup"
        ? {
            name: authForm.name.trim(),
            email: authForm.email.trim(),
            password: authForm.password,
            role: authForm.role
          }
        : {
            email: authForm.email.trim(),
            password: authForm.password
          };

    try {
      const response = await fetch(`${API_BASE}${authMode === "signup" ? "/auth/register" : "/auth/login"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        setAuthError(await readError(response, "Authentication failed."));
        return;
      }

      const data = await response.json();
      saveAuthSession(data.token, data.user);
      router.replace("/dashboard");
    } catch (error) {
      setAuthError("The server could not complete authentication. Please try again.");
    } finally {
      setAuthLoading(false);
    }
  }

  return (
    <main className="authPageShell">
      <section className="authHeroPanel">
        <div className="sectionBadge">Interview Pro</div>
        <h1>Professional AI interviews with secure proctoring</h1>
        <p>
          Train with role-based interviewers, track reports per account, and manage candidate activity from a
          polished admin workflow.
        </p>
        <div className="heroFeatureGrid">
          <article className="heroFeatureCard">
            <strong>Structured Practice</strong>
            <span>Role-specific mock interviews with guided scoring and feedback.</span>
          </article>
          <article className="heroFeatureCard">
            <strong>Secure Sessions</strong>
            <span>Account-based access, protected reports, and session persistence.</span>
          </article>
          <article className="heroFeatureCard">
            <strong>Live Proctoring</strong>
            <span>Browser-native webcam checks with low-friction candidate experience.</span>
          </article>
        </div>
      </section>

      <section className="authCard authCardWide">
        <div className="authEyebrow">Secure Interview Access</div>
        <h2>{authMode === "login" ? "Welcome back" : "Create your interview account"}</h2>
        <p>
          Candidate accounts can practice interviews and track their reports. Admin accounts can also review
          candidate activity across the platform.
        </p>

        <div className="authTabs">
          <button
            type="button"
            className={authMode === "login" ? "tabButton active" : "tabButton"}
            onClick={() => {
              setAuthMode("login");
              setAuthError("");
            }}
          >
            Login
          </button>
          <button
            type="button"
            className={authMode === "signup" ? "tabButton active" : "tabButton"}
            onClick={() => {
              setAuthMode("signup");
              setAuthError("");
            }}
          >
            Sign Up
          </button>
        </div>

        <form className="authForm" onSubmit={handleAuthSubmit}>
          {authMode === "signup" && (
            <input
              className="authInput"
              placeholder="Full name"
              value={authForm.name}
              onChange={(event) => setAuthForm((prev) => ({ ...prev, name: event.target.value }))}
            />
          )}
          <input
            className="authInput"
            type="email"
            placeholder="Email address"
            value={authForm.email}
            onChange={(event) => setAuthForm((prev) => ({ ...prev, email: event.target.value }))}
          />
          <input
            className="authInput"
            type="password"
            placeholder="Password"
            value={authForm.password}
            onChange={(event) => setAuthForm((prev) => ({ ...prev, password: event.target.value }))}
          />
          {authMode === "signup" && (
            <select
              className="authInput"
              value={authForm.role}
              onChange={(event) => setAuthForm((prev) => ({ ...prev, role: event.target.value }))}
            >
              <option value="candidate">Candidate account</option>
              <option value="admin">Admin account</option>
            </select>
          )}

          {authError && <div className="errorBanner">{authError}</div>}

          <button className="primaryButton authSubmit" type="submit" disabled={authLoading}>
            {authLoading ? "Working..." : authMode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>
      </section>
    </main>
  );
}
