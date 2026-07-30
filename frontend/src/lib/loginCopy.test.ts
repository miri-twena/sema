import { describe, expect, it } from "vitest";
import { detectBrowserLang, dirFor, LOGIN_COPY } from "./loginCopy";

describe("detectBrowserLang", () => {
  it("maps any Hebrew-tagged locale to he", () => {
    expect(detectBrowserLang("he")).toBe("he");
    expect(detectBrowserLang("he-IL")).toBe("he");
  });

  it("defaults everything else to en", () => {
    expect(detectBrowserLang("en-US")).toBe("en");
    expect(detectBrowserLang("fr")).toBe("en");
    expect(detectBrowserLang(undefined)).toBe("en");
  });
});

describe("dirFor", () => {
  it("is rtl only for he", () => {
    expect(dirFor("he")).toBe("rtl");
    expect(dirFor("en")).toBe("ltr");
  });
});

describe("LOGIN_COPY", () => {
  const ERROR_KINDS = ["uninvited", "suspended", "expired_invite", "provider_cancelled", "network_error"] as const;

  it("has every error message, non-empty, in both languages", () => {
    for (const lang of ["en", "he"] as const) {
      for (const kind of ERROR_KINDS) {
        const msg = LOGIN_COPY[lang].errors[kind]("demo@example.com");
        expect(msg.length).toBeGreaterThan(0);
      }
    }
  });

  it("interpolates the email into the uninvited message", () => {
    expect(LOGIN_COPY.en.errors.uninvited("someone@x.com")).toContain("someone@x.com");
    expect(LOGIN_COPY.he.errors.uninvited("someone@x.com")).toContain("someone@x.com");
  });

  it("wrongCode names the exact attempts remaining, and a distinct message at zero", () => {
    expect(LOGIN_COPY.en.wrongCode(3)).toContain("3");
    expect(LOGIN_COPY.en.wrongCode(0)).not.toContain("0");
    expect(LOGIN_COPY.he.wrongCode(3)).toContain("3");
  });

  it("every top-level copy key is non-empty in both languages", () => {
    for (const lang of ["en", "he"] as const) {
      const t = LOGIN_COPY[lang];
      expect(t.headline.length).toBeGreaterThan(0);
      expect(t.continueButton.length).toBeGreaterThan(0);
      expect(t.comingSoonTooltip.length).toBeGreaterThan(0);
      expect(t.troubleLink.length).toBeGreaterThan(0);
      expect(t.codeSentTo("a@x.com")).toContain("a@x.com");
      expect(t.resend.length).toBeGreaterThan(0);
      expect(t.changeEmail.length).toBeGreaterThan(0);
      expect(t.redirecting.length).toBeGreaterThan(0);
    }
  });
});
