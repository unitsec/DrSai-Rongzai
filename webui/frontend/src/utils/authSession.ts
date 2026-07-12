const TOKEN_KEY = "token";
const USER_EMAIL_KEY = "user_email";
const LEGACY_KEYS = ["username", "user_name"] as const;

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getUserEmail(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(USER_EMAIL_KEY);
}

function cancelAuthRefreshSchedule(): void {}

export function saveAuthSession(accessToken: string, userEmail: string): void {
  window.localStorage.setItem(TOKEN_KEY, accessToken);
  window.localStorage.setItem(USER_EMAIL_KEY, userEmail);
  for (const key of LEGACY_KEYS) {
    window.localStorage.removeItem(key);
  }
}

export function clearAuthSession(): void {
  cancelAuthRefreshSchedule();
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_EMAIL_KEY);
  for (const key of LEGACY_KEYS) {
    window.localStorage.removeItem(key);
  }
}

export type AuthVerifyResult =
  | { ok: true; userEmail: string; accessToken: string }
  | { ok: false };

export async function verifyAuthSession(): Promise<AuthVerifyResult> {
  const token = getAuthToken();
  const userEmail = getUserEmail();
  if (!token || !userEmail) {
    clearAuthSession();
    return { ok: false };
  }

  return { ok: true, userEmail, accessToken: token };
}

export function startAuthRefreshLoop(): void {
  return;
}

export function stopAuthRefreshLoop(): void {
  cancelAuthRefreshSchedule();
}
