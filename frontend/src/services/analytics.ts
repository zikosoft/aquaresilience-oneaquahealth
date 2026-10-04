/**
 * Google Analytics 4 (gtag.js), loaded only when a measurement id is configured.
 *
 * The id is read at runtime from `window.__APP_CONFIG__.GA_MEASUREMENT_ID`
 * (written into /runtime-config.js by the frontend container at startup from
 * the GA_MEASUREMENT_ID environment variable, so it can be changed after
 * deployment without rebuilding). `VITE_GA_MEASUREMENT_ID` is the fallback for
 * the Vite dev server. Without a valid id nothing is loaded and every call
 * below is a no-op.
 *
 * Page views are sent manually on each route change (this is a single-page
 * app, so GA's automatic page_view would only fire once).
 */

type EventParams = Record<string, string | number | boolean | undefined>

declare global {
  interface Window {
    __APP_CONFIG__?: { GA_MEASUREMENT_ID?: string }
    dataLayer?: unknown[]
    gtag?: (...args: unknown[]) => void
  }
}

const MEASUREMENT_ID_PATTERN = /^G-[A-Z0-9]{4,20}$/

let measurementId: string | null = null

function resolveMeasurementId(): string | null {
  const raw = window.__APP_CONFIG__?.GA_MEASUREMENT_ID || import.meta.env.VITE_GA_MEASUREMENT_ID || ''
  const id = String(raw).trim()
  return MEASUREMENT_ID_PATTERN.test(id) ? id : null
}

export function initAnalytics(): void {
  if (measurementId) return
  const id = resolveMeasurementId()
  if (!id) return
  measurementId = id

  window.dataLayer = window.dataLayer || []
  window.gtag = function gtag(): void {
    // gtag.js requires the `arguments` object itself, not an array copy.
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer?.push(arguments)
  }
  window.gtag('js', new Date())
  window.gtag('config', id, { send_page_view: false })

  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`
  document.head.appendChild(script)
}

export function trackPageView(path: string, title: string): void {
  if (!measurementId || !window.gtag) return
  window.gtag('event', 'page_view', {
    page_path: path,
    page_title: title,
    page_location: `${window.location.origin}${path}`,
  })
}

export function trackEvent(name: string, params: EventParams = {}): void {
  if (!measurementId || !window.gtag) return
  window.gtag('event', name, params)
}
