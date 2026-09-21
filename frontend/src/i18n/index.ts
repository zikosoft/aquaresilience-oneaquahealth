import { createI18n } from 'vue-i18n'

import en from './locales/en'
import es from './locales/es'
import fr from './locales/fr'

export type AppLocale = 'en' | 'fr' | 'es'

export const SUPPORTED_LOCALES: { code: AppLocale; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'es', label: 'Español' },
]

const STORAGE_KEY = 'aquaresilience.locale'

function detectInitialLocale(): AppLocale {
  const stored = localStorage.getItem(STORAGE_KEY) as AppLocale | null
  if (stored && SUPPORTED_LOCALES.some((l) => l.code === stored)) return stored

  const browserLang = navigator.language.slice(0, 2)
  if (SUPPORTED_LOCALES.some((l) => l.code === browserLang)) return browserLang as AppLocale

  return (import.meta.env.VITE_DEFAULT_LOCALE as AppLocale) || 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectInitialLocale(),
  fallbackLocale: 'en',
  messages: { en, fr, es },
})

export function setLocale(locale: AppLocale): void {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.setAttribute('lang', locale)
}
