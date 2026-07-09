import { createSign } from "node:crypto";

export const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
export const SHEETS_API_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets";
export const SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";
export const SHEETS_WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets";

export function readEnv(name, fallback = "") {
  return String(process.env[name] || fallback || "").trim();
}

export function normalizePrivateKey(value) {
  return String(value || "").replace(/\\n/g, "\n").trim();
}

export function parseServiceAccountJson() {
  const rawJson = readEnv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON");
  if (rawJson) {
    const parsed = JSON.parse(rawJson);
    return {
      clientEmail: String(parsed.client_email || "").trim(),
      privateKey: normalizePrivateKey(parsed.private_key),
    };
  }

  return {
    clientEmail: readEnv("GOOGLE_SHEETS_CLIENT_EMAIL"),
    privateKey: normalizePrivateKey(readEnv("GOOGLE_SHEETS_PRIVATE_KEY")),
  };
}

export function base64UrlEncode(value) {
  return Buffer.from(value)
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

export function createJwt(serviceAccount, scope) {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const header = {
    alg: "RS256",
    typ: "JWT",
  };
  const claims = {
    iss: serviceAccount.clientEmail,
    scope,
    aud: GOOGLE_TOKEN_URL,
    exp: nowSeconds + 3600,
    iat: nowSeconds,
  };
  const unsignedToken = `${base64UrlEncode(JSON.stringify(header))}.${base64UrlEncode(JSON.stringify(claims))}`;
  const signer = createSign("RSA-SHA256");
  signer.update(unsignedToken);
  signer.end();
  const signature = signer
    .sign(serviceAccount.privateKey, "base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `${unsignedToken}.${signature}`;
}

export async function requestAccessToken(serviceAccount, scope) {
  const assertion = createJwt(serviceAccount, scope);
  const response = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion,
    }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`Google OAuth token 取得失敗：HTTP ${response.status} ${payload.error || ""}`.trim());
  }

  const token = String(payload.access_token || "").trim();
  if (!token) {
    throw new Error("Google OAuth token 回應缺少 access_token。");
  }
  return token;
}

export function quoteSheetRange(sheetName, columns) {
  const escapedSheetName = String(sheetName || "pending").replace(/'/g, "''");
  return `'${escapedSheetName}'!${columns || "A:Z"}`;
}

export async function readSheetValues({ spreadsheetId, sheetName, columns, accessToken }) {
  const range = quoteSheetRange(sheetName, columns);
  const url = `${SHEETS_API_BASE_URL}/${encodeURIComponent(spreadsheetId)}/values/${encodeURIComponent(range)}`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`Google Sheets API 讀取待收錄名單失敗：HTTP ${response.status} ${payload.error?.message || ""}`.trim());
  }
  return Array.isArray(payload.values) ? payload.values : [];
}

export async function batchUpdateSheetValues({ spreadsheetId, accessToken, data }) {
  if (!Array.isArray(data) || data.length === 0) {
    return {
      totalUpdatedCells: 0,
      totalUpdatedRows: 0,
      totalUpdatedSheets: 0,
    };
  }

  const url = `${SHEETS_API_BASE_URL}/${encodeURIComponent(spreadsheetId)}/values:batchUpdate`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      valueInputOption: "RAW",
      data,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`Google Sheets API 更新待收錄名單失敗：HTTP ${response.status} ${payload.error?.message || ""}`.trim());
  }
  return payload;
}
