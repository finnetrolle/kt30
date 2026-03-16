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

export function applyBrowserCompatibilityMode() {
  if (!shouldUseBrowserCompatibilityMode() || typeof document === "undefined") {
    return;
  }

  document.documentElement.classList.add("browser-lite");
}
