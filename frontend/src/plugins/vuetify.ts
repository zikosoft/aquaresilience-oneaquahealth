import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

import { createVuetify, type ThemeDefinition } from 'vuetify'

// Components/directives are auto-registered per use-site by
// `vite-plugin-vuetify`'s `autoImport` (see vite.config.ts), so no manual
// barrel import of `vuetify/components` / `vuetify/directives` is needed
// here — importing those full barrels forces TypeScript to fully resolve
// vuetify's entire (very large) component type surface for this file.

// AquaResilience monitoring palette: deep hydrology blues + a resilience teal
// accent, tuned for readability on an operations-center display in both
// light and dark contexts. Severity colors map 1:1 to the deterministic risk
// categories used across the platform (P2+): LOW/MODERATE/HIGH/CRITICAL.
const lightTheme: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#F4F7FA',
    surface: '#FFFFFF',
    primary: '#0B5FA5',
    'primary-darken-1': '#084A82',
    secondary: '#106E7C',
    accent: '#1FB6C9',
    error: '#D64550',
    info: '#2A8FD6',
    success: '#2E9E5B',
    warning: '#E0A31D',
    'risk-low': '#2E9E5B',
    'risk-moderate': '#E0A31D',
    'risk-high': '#E0672B',
    'risk-critical': '#D64550',
  },
}

const darkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0B1622',
    surface: '#101E2E',
    primary: '#3F9CE8',
    'primary-darken-1': '#2A7FC4',
    secondary: '#2FB0C2',
    accent: '#4FD6E8',
    error: '#F1707A',
    info: '#5AAEEA',
    success: '#4CC780',
    warning: '#F0BE4C',
    'risk-low': '#4CC780',
    'risk-moderate': '#F0BE4C',
    'risk-high': '#F2915A',
    'risk-critical': '#F1707A',
  },
}

export const vuetify = createVuetify({
  theme: {
    defaultTheme: 'light',
    themes: {
      light: lightTheme,
      dark: darkTheme,
    },
  },
  defaults: {
    VCard: { rounded: 'lg' },
    VBtn: { rounded: 'lg' },
    VTextField: { variant: 'outlined', density: 'comfortable' },
    VSelect: { variant: 'outlined', density: 'comfortable' },
  },
})
