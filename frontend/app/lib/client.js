export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "https://backend-intervora.onrender.com";
export const TOKEN_STORAGE_KEY = "interview-pro-token";
export const USER_STORAGE_KEY = "interview-pro-user";
export const INTERVIEW_STORAGE_KEY = "interview-pro-active-interview";

export const STATUS_STYLES = {
  clear: "statusClear",
  low_visibility: "statusWarn",
  no_face: "statusDanger",
  multiple_faces: "statusDanger",
  phone_detected: "statusDanger",
  restricted_object: "statusWarn"
};

export function buildEmptyStats() {
  return {
    clear: 0,
    no_face: 0,
    multiple_faces: 0,
    low_visibility: 0,
    phone_detected: 0,
    restricted_object: 0
  };
}

export function buildInitialAuthForm() {
  return {
    name: "",
    email: "",
    password: "",
    role: "candidate"
  };
}

export function normalizeErrorMessage(detail, fallbackMessage) {
  if (!detail) return fallbackMessage;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => normalizeErrorMessage(item, ""))
      .filter(Boolean);
    return messages.length ? messages.join(" ") : fallbackMessage;
  }

  if (typeof detail === "object") {
    if (typeof detail.msg === "string") {
      const location = Array.isArray(detail.loc) ? detail.loc.join(" > ") : "";
      return location ? `${location}: ${detail.msg}` : detail.msg;
    }

    if (typeof detail.detail === "string") {
      return detail.detail;
    }
  }

  return fallbackMessage;
}

export async function readError(response, fallbackMessage) {
  try {
    const data = await response.json();
    return normalizeErrorMessage(data.detail, fallbackMessage);
  } catch (error) {
    return fallbackMessage;
  }
}

export async function authorizedFetch(path, options = {}, activeToken = "") {
  const headers = new Headers(options.headers || {});
  if (activeToken) {
    headers.set("Authorization", `Bearer ${activeToken}`);
  }

  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  });
}

export function getStoredToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

export function getStoredUser() {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(USER_STORAGE_KEY);
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch (error) {
    return null;
  }
}

export function saveAuthSession(token, user) {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

export function clearAuthSession() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(USER_STORAGE_KEY);
}

export function getStoredInterviewSession() {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(INTERVIEW_STORAGE_KEY);
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch (error) {
    return null;
  }
}

export function saveInterviewSession(payload) {
  window.localStorage.setItem(INTERVIEW_STORAGE_KEY, JSON.stringify(payload));
}

export function clearInterviewSession() {
  window.localStorage.removeItem(INTERVIEW_STORAGE_KEY);
}

export async function fetchCurrentUser(token) {
  const response = await authorizedFetch("/auth/me", {}, token);
  if (!response.ok) {
    throw new Error("Authentication required.");
  }
  return response.json();
}

export async function fetchDashboardBundle(token, currentUser) {
  const historyResponse = await authorizedFetch("/api/interviews/mine", {}, token);
  const historyItems = historyResponse.ok ? await historyResponse.json() : [];

  if (currentUser?.role !== "admin") {
    return {
      historyItems,
      adminDashboard: null,
      adminUsers: [],
      adminItems: []
    };
  }

  const [dashboardResponse, usersResponse, interviewsResponse] = await Promise.all([
    authorizedFetch("/api/admin/dashboard", {}, token),
    authorizedFetch("/api/admin/users", {}, token),
    authorizedFetch("/api/admin/interviews", {}, token)
  ]);

  return {
    historyItems,
    adminDashboard: dashboardResponse.ok ? await dashboardResponse.json() : null,
    adminUsers: usersResponse.ok ? await usersResponse.json() : [],
    adminItems: interviewsResponse.ok ? await interviewsResponse.json() : []
  };
}

export function formatDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
}

export function isFeedbackReport(content) {
  return content.includes("# Interview Performance Report") || content.includes("## Proctoring Summary");
}
