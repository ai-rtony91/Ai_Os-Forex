import { RUNTIME_VISIBILITY_SOURCE_LABELS } from "./runtimeVisibilityAdapter.js";

const RUNTIME_VISIBILITY_API_SCHEMA = "aios.runtime_visibility_api.v1";
const READ_ONLY_MODE = "READ_ONLY";

export const RUNTIME_VISIBILITY_STATES = Object.freeze({
  AVAILABLE: "available",
  UNAVAILABLE: "unavailable",
  STALE: "stale",
  INVALID: "invalid"
});

export const RUNTIME_VISIBILITY_CLIENT_ERROR_CODES = Object.freeze({
  API_UNAVAILABLE: "API_UNAVAILABLE",
  HTTP_ERROR: "HTTP_ERROR",
  INVALID_RESPONSE: "INVALID_RESPONSE",
  INVALID_SCHEMA: "INVALID_SCHEMA",
  NON_READ_ONLY_RESPONSE: "NON_READ_ONLY_RESPONSE",
  REQUEST_TIMEOUT: "REQUEST_TIMEOUT",
  UNKNOWN: "UNKNOWN"
});

export const DEFAULT_RUNTIME_VISIBILITY_CONFIG = Object.freeze({
  sourceLabel: RUNTIME_VISIBILITY_SOURCE_LABELS.MOCK_DATA,
  apiUrl: "/api/runtime/visibility",
  timeoutMs: 3000
});

export function getRuntimeVisibilityClientConfig(env = import.meta.env) {
  return {
    sourceLabel:
      env?.VITE_AIOS_RUNTIME_VISIBILITY_SOURCE ??
      DEFAULT_RUNTIME_VISIBILITY_CONFIG.sourceLabel,
    apiUrl:
      env?.VITE_AIOS_RUNTIME_VISIBILITY_URL ??
      DEFAULT_RUNTIME_VISIBILITY_CONFIG.apiUrl,
    timeoutMs: Number(
      env?.VITE_AIOS_RUNTIME_VISIBILITY_TIMEOUT_MS ??
        DEFAULT_RUNTIME_VISIBILITY_CONFIG.timeoutMs
    )
  };
}

function runtimeStateForError(error) {
  if ([
    RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.API_UNAVAILABLE,
    RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.HTTP_ERROR,
    RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.REQUEST_TIMEOUT
  ].includes(error?.code)) {
    return RUNTIME_VISIBILITY_STATES.UNAVAILABLE;
  }
  return RUNTIME_VISIBILITY_STATES.INVALID;
}

export function createRuntimeVisibilityErrorState(error) {
  return {
    sourceLabel: RUNTIME_VISIBILITY_SOURCE_LABELS.UNKNOWN,
    runtimeState: runtimeStateForError(error),
    loading: false,
    data: null,
    error: {
      code: error?.code ?? RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.UNKNOWN,
      message: error?.message ?? "Runtime visibility source is unavailable."
    }
  };
}

export function validateRuntimeVisibilityApiSchema(data) {
  if (data?.schema !== RUNTIME_VISIBILITY_API_SCHEMA) {
    return {
      ok: false,
      code: RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.INVALID_SCHEMA,
      message: "Runtime visibility API returned an unexpected schema."
    };
  }

  if (data?.mode !== READ_ONLY_MODE) {
    return {
      ok: false,
      code: RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.NON_READ_ONLY_RESPONSE,
      message: "Runtime visibility API response was not read-only."
    };
  }

  return { ok: true, code: null, message: null };
}

export async function fetchRuntimeVisibilityReadOnly(config = getRuntimeVisibilityClientConfig()) {
  const controller = new AbortController();
  const timeoutMs = Number.isFinite(config.timeoutMs) && config.timeoutMs > 0
    ? config.timeoutMs
    : DEFAULT_RUNTIME_VISIBILITY_CONFIG.timeoutMs;
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    let response;
    try {
      response = await fetch(config.apiUrl, { method: "GET", signal: controller.signal });
    } catch (error) {
      throw {
        code: error?.name === "AbortError"
          ? RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.REQUEST_TIMEOUT
          : RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.API_UNAVAILABLE,
        message: error?.name === "AbortError"
          ? "Runtime visibility request timed out."
          : "Runtime visibility API is unavailable."
      };
    }

    if (response.status === 503) {
      throw {
        code: RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.API_UNAVAILABLE,
        message: "Runtime visibility API is unavailable."
      };
    }

    if (!response.ok) {
      throw {
        code: RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.HTTP_ERROR,
        message: `Runtime visibility API returned HTTP ${response.status}.`
      };
    }

    let data;
    try {
      data = await response.json();
    } catch {
      throw {
        code: RUNTIME_VISIBILITY_CLIENT_ERROR_CODES.INVALID_RESPONSE,
        message: "Runtime visibility API returned invalid JSON."
      };
    }

    const validation = validateRuntimeVisibilityApiSchema(data);
    if (!validation.ok) throw validation;

    const isStale = Boolean(
      data?.frontend_contract?.freshness?.is_stale ??
      data?.frontend_contract?.stale_or_legacy
    );

    return {
      sourceLabel: RUNTIME_VISIBILITY_SOURCE_LABELS.LOCAL_API_READ_ONLY,
      runtimeState: isStale
        ? RUNTIME_VISIBILITY_STATES.STALE
        : RUNTIME_VISIBILITY_STATES.AVAILABLE,
      loading: false,
      data,
      error: null
    };
  } finally {
    clearTimeout(timeout);
  }
}
