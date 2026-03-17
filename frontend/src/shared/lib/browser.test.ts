import { describe, expect, it, vi } from "vitest";

describe("browser compatibility mode", () => {
  it("detects Safari and applies compatibility class", async () => {
    vi.stubGlobal(
      "navigator",
      {
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc."
      } satisfies Partial<Navigator>
    );

    const { applyBrowserCompatibilityMode, shouldUseBrowserCompatibilityMode } = await import("@/shared/lib/browser");

    expect(shouldUseBrowserCompatibilityMode()).toBe(true);
    applyBrowserCompatibilityMode();
    expect(document.documentElement.classList.contains("browser-lite")).toBe(true);
  });

  it("does not enable compatibility mode for Chromium browsers", async () => {
    vi.stubGlobal(
      "navigator",
      {
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        vendor: "Google Inc."
      } satisfies Partial<Navigator>
    );

    const { shouldUseBrowserCompatibilityMode } = await import("@/shared/lib/browser");

    expect(shouldUseBrowserCompatibilityMode()).toBe(false);
  });

  it("uses safer polling intervals in compatibility mode", async () => {
    const { resolveTaskPollingInterval } = await import("@/shared/lib/browser");

    expect(resolveTaskPollingInterval(true, true)).toBe(45000);
    expect(resolveTaskPollingInterval(true, false)).toBe(120000);
    expect(resolveTaskPollingInterval(false, true)).toBe(3000);
  });
});
