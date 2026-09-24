import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchCities } from '@/services/geographyApi'
import type { City } from '@/types'

const CITY_KEY = 'aquaresilience.city_id'

// Session 018 (user request): the header's city selector. Every
// dashboard-facing view reads `selectedCity`/`selectedCityId` from here and
// passes `city_id` to its API calls — the backend returns the exact same
// response shape for any city (see app/services/city_context.py), just
// with `data_available: false` for the 8 consortium cities that don't have
// a live connector yet. Toulouse (the one real city) stays the default so
// a fresh visit — and every existing screenshot/demo path — behaves
// exactly as before.
export const useCityStore = defineStore('city', () => {
  const cities = ref<City[]>([])
  const selectedCityId = ref<string | null>(localStorage.getItem(CITY_KEY))
  const loaded = ref(false)

  const selectedCity = computed<City | null>(() => {
    if (!cities.value.length) return null
    return cities.value.find((c) => c.id === selectedCityId.value) ?? demoCity.value ?? cities.value[0]
  })

  const demoCity = computed<City | null>(() => cities.value.find((c) => c.has_live_data) ?? null)

  async function load(): Promise<void> {
    if (loaded.value) return
    try {
      cities.value = await fetchCities()
      // First visit (nothing in localStorage yet): default to the live
      // demo city, not just whichever city happens to sort first.
      if (!selectedCityId.value) {
        selectedCityId.value = demoCity.value?.id ?? cities.value[0]?.id ?? null
      }
      loaded.value = true
    } catch {
      // Never let a geography fetch failure block the app — the map and
      // dashboard already have their own Toulouse fallbacks.
      loaded.value = true
    }
  }

  function selectCity(cityId: string): void {
    selectedCityId.value = cityId
    localStorage.setItem(CITY_KEY, cityId)
  }

  return { cities, selectedCityId, selectedCity, demoCity, loaded, load, selectCity }
})
