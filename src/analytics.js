const measurementId = (import.meta.env.VITE_GA_MEASUREMENT_ID || "").trim();
const enableInDev = import.meta.env.VITE_GA_ENABLE_IN_DEV === "true";

function canUseAnalytics() {
  if (!measurementId) {
    return false;
  }

  if (import.meta.env.DEV && !enableInDev) {
    return false;
  }

  return typeof window !== "undefined" && typeof document !== "undefined";
}

export function initAnalytics() {
  if (!canUseAnalytics() || window.__ffxivTcAnalyticsInitialized) {
    return;
  }

  window.__ffxivTcAnalyticsInitialized = true;
  window.dataLayer = window.dataLayer || [];
  window.gtag =
    window.gtag ||
    function gtag() {
      window.dataLayer.push(arguments);
    };

  window.gtag("js", new Date());
  window.gtag("config", measurementId);

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.appendChild(script);
}

export function trackEvent(eventName, params = {}) {
  if (!canUseAnalytics() || typeof window.gtag !== "function") {
    return;
  }

  window.gtag("event", eventName, params);
}

export function getAnalyticsMeasurementId() {
  return measurementId;
}
