function userAgent() {
  if (typeof navigator === "undefined") {
    return "";
  }

  return navigator.userAgent ?? "";
}

function vendor() {
  if (typeof navigator === "undefined") {
    return "";
  }

  return navigator.vendor ?? "";
}

export function isSafariLikeBrowser() {
  const ua = userAgent();
  const browserVendor = vendor();

  if (!ua) {
    return false;
  }

  const isSafariEngine = /Safari/i.test(ua) && /Apple/i.test(browserVendor);
  const hasChromiumOrFirefoxSignature = /Chrome|Chromium|CriOS|Edg|OPR|FxiOS|Firefox|SamsungBrowser/i.test(ua);

  return isSafariEngine && !hasChromiumOrFirefoxSignature;
}

export function shouldUseBrowserCompatibilityMode() {
  return isSafariLikeBrowser();
}

export function isDocumentVisible() {
  if (typeof document === "undefined") {
    return true;
  }

  return document.visibilityState !== "hidden";
}

export function resolveTaskPollingInterval(compatibilityMode: boolean, visible = true) {
  if (!visible) {
    return compatibilityMode ? 120000 : 10000;
  }

  return compatibilityMode ? 45000 : 3000;
}

export function resolveDashboardPollingInterval(compatibilityMode: boolean, visible = true) {
  if (!visible) {
    return compatibilityMode ? 60000 : 15000;
  }

  return compatibilityMode ? 30000 : 4000;
}

export function applyBrowserCompatibilityMode() {
  if (!shouldUseBrowserCompatibilityMode() || typeof document === "undefined") {
    return;
  }

  document.documentElement.classList.add("browser-lite");
}
