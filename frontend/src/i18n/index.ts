import { createI18n } from 'vue-i18n'

import de from './locales/de'
import el from './locales/el'
import en from './locales/en'
import es from './locales/es'
import fr from './locales/fr'
import it from './locales/it'
import nl from './locales/nl'
import no from './locales/no'
import pt from './locales/pt'

// Session 018 (user request): one language per OneAquaHealth consortium
// country that doesn't already have one (Spain=es, France=fr were already
// covered) — Portugal/Coimbra, Norway/Oslo, Greece, Austria/Vienna (German),
// Italy/Naples, Belgium/Ghent (Dutch, the language of Flanders where Ghent
// sits — French already covers Wallonia/Brussels). Hebrew (Israel) is
// deliberately excluded: it needs RTL layout support, a materially bigger
// change than adding another LTR JSON locale — a separate follow-up.
export type AppLocale = 'en' | 'fr' | 'es' | 'pt' | 'no' | 'el' | 'de' | 'it' | 'nl'

// Flags are a visual affordance per the user's request ("plus vendeur") —
// purely cosmetic, English intentionally uses a neutral globe rather than
// a single national flag since it isn't tied to one consortium country.
export const SUPPORTED_LOCALES: { code: AppLocale; label: string; flag: string }[] = [
  { code: 'en', label: 'English', flag: '🌐' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
  { code: 'es', label: 'Español', flag: '🇪🇸' },
  { code: 'pt', label: 'Português', flag: '🇵🇹' },
  { code: 'no', label: 'Norsk', flag: '🇳🇴' },
  { code: 'el', label: 'Ελληνικά', flag: '🇬🇷' },
  { code: 'de', label: 'Deutsch', flag: '🇦🇹' },
  { code: 'it', label: 'Italiano', flag: '🇮🇹' },
  { code: 'nl', label: 'Nederlands', flag: '🇧🇪' },
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
  messages: { en, fr, es, pt, no, el, de, it, nl },
})

export function setLocale(locale: AppLocale): void {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.setAttribute('lang', locale)
}
