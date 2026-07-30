import { describe, expect, it } from "vitest";
import { INITIAL_LOGIN_STATE, loginReducer, type DevPreset } from "./useLoginFlow";

const ALL_PRESETS: DevPreset[] = [
  "code_sent",
  "wrong_code",
  "code_expired",
  "uninvited",
  "suspended",
  "expired_invite",
  "network_error",
];

describe("loginReducer", () => {
  it("moves from email to code on CODE_SENT, carrying the email forward", () => {
    const withEmail = loginReducer(INITIAL_LOGIN_STATE, { type: "EMAIL_CHANGE", email: "a@x.com" });
    const sent = loginReducer(withEmail, { type: "CODE_SENT" });
    expect(sent.step).toBe("code");
    expect(sent.email).toBe("a@x.com");
    expect(sent.resendCooldown).toBeGreaterThan(0);
    expect(sent.attemptsLeft).toBe(5);
  });

  it("decrements attemptsLeft on WRONG_CODE and never goes below zero", () => {
    let s = loginReducer(INITIAL_LOGIN_STATE, { type: "CODE_SENT" });
    for (let i = 0; i < 7; i++) s = loginReducer(s, { type: "WRONG_CODE" });
    expect(s.attemptsLeft).toBe(0);
    expect(s.codeError).toBe("wrong_code");
  });

  it("RESEND_DONE clears any code error and resets attempts + cooldown", () => {
    let s = loginReducer(INITIAL_LOGIN_STATE, { type: "CODE_SENT" });
    s = loginReducer(s, { type: "WRONG_CODE" });
    s = loginReducer(s, { type: "RESEND_START" });
    s = loginReducer(s, { type: "RESEND_DONE" });
    expect(s.codeError).toBeNull();
    expect(s.attemptsLeft).toBe(5);
    expect(s.resendCooldown).toBeGreaterThan(0);
  });

  it("RESEND_TICK counts down but never below zero", () => {
    let s = { ...INITIAL_LOGIN_STATE, resendCooldown: 1 };
    s = loginReducer(s, { type: "RESEND_TICK" });
    expect(s.resendCooldown).toBe(0);
    s = loginReducer(s, { type: "RESEND_TICK" });
    expect(s.resendCooldown).toBe(0);
  });

  it("CHANGE_EMAIL resets to the email step but keeps the typed address", () => {
    let s = loginReducer(INITIAL_LOGIN_STATE, { type: "EMAIL_CHANGE", email: "a@x.com" });
    s = loginReducer(s, { type: "CODE_SENT" });
    s = loginReducer(s, { type: "CHANGE_EMAIL" });
    expect(s.step).toBe("email");
    expect(s.email).toBe("a@x.com");
  });

  it("VERIFY_SUCCESS moves to the redirecting step", () => {
    const s = loginReducer(INITIAL_LOGIN_STATE, { type: "VERIFY_SUCCESS" });
    expect(s.step).toBe("redirecting");
  });

  it.each(ALL_PRESETS)("FORCE_PRESET %s lands on a coherent, renderable state", (preset) => {
    const s = loginReducer(INITIAL_LOGIN_STATE, { type: "FORCE_PRESET", preset });
    expect(["email", "code", "error", "redirecting"]).toContain(s.step);
    if (s.step === "error") expect(s.errorKind).not.toBeNull();
    if (s.step === "code" && s.codeError) expect(["wrong_code", "code_expired"]).toContain(s.codeError);
  });

  it("RESET returns to the initial state", () => {
    const dirty = loginReducer(INITIAL_LOGIN_STATE, { type: "FORCE_PRESET", preset: "suspended" });
    expect(loginReducer(dirty, { type: "RESET" })).toEqual(INITIAL_LOGIN_STATE);
  });
});
