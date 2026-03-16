import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  document.documentElement.classList.remove("browser-lite");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
