import { useEffect, useReducer } from "react";
import type { ErrorKind } from "../lib/loginCopy";

const MAX_ATTEMPTS = 5;
const RESEND_COOLDOWN_SECONDS = 60;
// Mock network latency for the "Continue"/verify round trips -- long enough
// to see the loading state, short enough not to feel broken.
export const MOCK_DELAY_MS = 700;

export type LoginStep = "email" | "code" | "error" | "redirecting";

/** Every state the dev-only panel can jump to directly, for review without
 * driving the full flow by hand (auth_login_prompt.md Part 0, item 0.3). */
export type DevPreset =
  | "code_sent"
  | "wrong_code"
  | "code_expired"
  | "uninvited"
  | "suspended"
  | "expired_invite"
  | "network_error";

export interface LoginState {
  step: LoginStep;
  email: string;
  emailSubmitting: boolean;
  code: string;
  codeError: "wrong_code" | "code_expired" | null;
  attemptsLeft: number;
  verifying: boolean;
  resending: boolean;
  resendCooldown: number;
  errorKind: ErrorKind | null;
}

export const INITIAL_LOGIN_STATE: LoginState = {
  step: "email",
  email: "",
  emailSubmitting: false,
  code: "",
  codeError: null,
  attemptsLeft: MAX_ATTEMPTS,
  verifying: false,
  resending: false,
  resendCooldown: 0,
  errorKind: null,
};

export type LoginAction =
  | { type: "EMAIL_CHANGE"; email: string }
  | { type: "SUBMIT_EMAIL" }
  | { type: "CODE_SENT" }
  | { type: "CODE_CHANGE"; code: string }
  | { type: "VERIFY_START" }
  | { type: "VERIFY_SUCCESS" }
  | { type: "WRONG_CODE" }
  | { type: "RESEND_START" }
  | { type: "RESEND_DONE" }
  | { type: "RESEND_TICK" }
  | { type: "CHANGE_EMAIL" }
  | { type: "FORCE_PRESET"; preset: DevPreset }
  | { type: "RESET" };

/** Pure reducer -- exported (not just used inside the hook) so it's directly
 * unit-testable without rendering anything, same rationale as e.g.
 * sema_core's pure functions on the backend side. */
export function loginReducer(state: LoginState, action: LoginAction): LoginState {
  switch (action.type) {
    case "EMAIL_CHANGE":
      return { ...state, email: action.email };

    case "SUBMIT_EMAIL":
      return { ...state, emailSubmitting: true };

    case "CODE_SENT":
      return {
        ...INITIAL_LOGIN_STATE,
        step: "code",
        email: state.email,
        resendCooldown: RESEND_COOLDOWN_SECONDS,
      };

    case "CODE_CHANGE":
      return { ...state, code: action.code, codeError: null };

    case "VERIFY_START":
      return { ...state, verifying: true };

    case "VERIFY_SUCCESS":
      return { ...state, step: "redirecting", verifying: false };

    case "WRONG_CODE": {
      const attemptsLeft = Math.max(0, state.attemptsLeft - 1);
      return { ...state, verifying: false, code: "", codeError: "wrong_code", attemptsLeft };
    }

    case "RESEND_START":
      return { ...state, resending: true };

    case "RESEND_DONE":
      return {
        ...state,
        resending: false,
        code: "",
        codeError: null,
        attemptsLeft: MAX_ATTEMPTS,
        resendCooldown: RESEND_COOLDOWN_SECONDS,
      };

    case "RESEND_TICK":
      return { ...state, resendCooldown: Math.max(0, state.resendCooldown - 1) };

    case "CHANGE_EMAIL":
      return { ...INITIAL_LOGIN_STATE, email: state.email };

    case "FORCE_PRESET":
      return applyPreset(state, action.preset);

    case "RESET":
      return INITIAL_LOGIN_STATE;

    default:
      return state;
  }
}

function applyPreset(state: LoginState, preset: DevPreset): LoginState {
  const email = state.email || "demo@example.com";
  switch (preset) {
    case "code_sent":
      return { ...INITIAL_LOGIN_STATE, step: "code", email, resendCooldown: RESEND_COOLDOWN_SECONDS };
    case "wrong_code":
      return {
        ...INITIAL_LOGIN_STATE,
        step: "code",
        email,
        codeError: "wrong_code",
        attemptsLeft: 3,
        resendCooldown: 34,
      };
    case "code_expired":
      return {
        ...INITIAL_LOGIN_STATE,
        step: "code",
        email,
        codeError: "code_expired",
        resendCooldown: 0,
      };
    case "uninvited":
      return { ...INITIAL_LOGIN_STATE, step: "error", errorKind: "uninvited", email };
    case "suspended":
      return { ...INITIAL_LOGIN_STATE, step: "error", errorKind: "suspended", email };
    case "expired_invite":
      return { ...INITIAL_LOGIN_STATE, step: "error", errorKind: "expired_invite", email };
    case "network_error":
      return { ...INITIAL_LOGIN_STATE, step: "error", errorKind: "network_error", email };
    default:
      return state;
  }
}

/** Drives the login page's local state machine with mocked async responses
 * (no backend in Part 0 -- see auth_login_prompt.md). Every "network" step
 * resolves after MOCK_DELAY_MS so the loading states are actually visible,
 * then always succeeds on the normal path (the dev panel is how each error
 * state gets reviewed, not magic input values). */
export function useLoginFlow() {
  const [state, dispatch] = useReducer(loginReducer, INITIAL_LOGIN_STATE);

  // The 60s resend cooldown ticks down once a second while on the code step.
  useEffect(() => {
    if (state.step !== "code" || state.resendCooldown <= 0) return;
    const id = window.setInterval(() => dispatch({ type: "RESEND_TICK" }), 1000);
    return () => window.clearInterval(id);
  }, [state.step, state.resendCooldown]);

  // Auto-verify once the code reaches 6 digits, mirroring a real OTP input.
  useEffect(() => {
    if (state.step !== "code" || state.code.length !== 6 || state.verifying) return;
    dispatch({ type: "VERIFY_START" });
    const id = window.setTimeout(() => dispatch({ type: "VERIFY_SUCCESS" }), MOCK_DELAY_MS);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.code]);

  const submitEmail = (email: string) => {
    dispatch({ type: "EMAIL_CHANGE", email });
    dispatch({ type: "SUBMIT_EMAIL" });
    window.setTimeout(() => dispatch({ type: "CODE_SENT" }), MOCK_DELAY_MS);
  };

  const resend = () => {
    dispatch({ type: "RESEND_START" });
    window.setTimeout(() => dispatch({ type: "RESEND_DONE" }), MOCK_DELAY_MS);
  };

  return {
    state,
    dispatch,
    submitEmail,
    setCode: (code: string) => dispatch({ type: "CODE_CHANGE", code }),
    resend,
    changeEmail: () => dispatch({ type: "CHANGE_EMAIL" }),
    forcePreset: (preset: DevPreset) => dispatch({ type: "FORCE_PRESET", preset }),
  };
}
