import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchCities } from '@/services/geographyApi'
import type { City } from '@/types'

const CITY_KEY = 'aquaresilience.city_id'

// Session 018 (user request): the header's city selector. Every
// dashboard-facing view reads `selectedCity`/`selectedCityId` from here and
// passes `city_id` to its API calls — the backend returns the exact same
// response shape for any city (see app/services/city_context.py), just
// with `data_available: false` for the consortium cities that don't have a
// live connector yet.
export const useCityStore = defineStore('city', () => {
  const cities = ref<City[]>([])
  const selectedCityId = ref<string | null>(localStorage.getItem(CITY_KEY))
  const loaded = ref(false)

  const selectedCity = computed<City | null>(() => {
    if (!cities.value.length) return null
    return cities.value.find((c) => c.id === selectedCityId.value) ?? demoCity.value ?? cities.value[0]
  })

  // Session 020 fix (live-caught): now that Vienna/Ghent are live too, this
  // used to resolve to "whichever live city sorts first alphabetically" —
  // Ghent, not Toulouse, for a brand new visitor with nothing in
  // localStorage yet, quietly changing the app's own default landing city
  // as a side effect of onboarding more cities, never a deliberate choice.
  // Toulouse — this hackathon's actual demo subject, Track 6's flagship
  // "Toulouse Métropole" city — now stays the explicit first choice
  // whenever it's live, falling back to the old "first live city"
  // behavior only if it somehow isn't (defensive, should never happen).
  const demoCity = computed<City | null>(
    () => cities.value.find((c) => c.has_live_data && c.label_en === 'Toulouse') ?? cities.value.find((c) => c.has_live_data) ?? null,
  )

  async function load(): Promise<void> {
    if (loaded.value) return
    try {
      cities.value = await fetchCities()
      // Session 021 fix (user report): "la carte reste tout le temps
      // pointée sur Toulouse" / "on ne voit plus les elements" — root
      // cause was that `selectedCityId` (the raw id, read once from
      // localStorage) never self-corrected when it stopped matching any
      // currently-loaded city (e.g. a dev DB reset regenerates city UUIDs,
      // orphaning whatever id was cached in the browser from before).
      // `selectedCity` below already has a graceful fallback for exactly
      // this case, so the header itself kept showing "Toulouse" — but
      // every map/dashboard/scenario call reads `selectedCityId` directly
      // (see its own doc comment), and that raw id was never healed to
      // match, silently sending a city_id that matches nothing (→ 0
      // stations, 0 markers) instead of the same fallback the header
      // displays. Covers both "nothing in localStorage yet" (the original
      // check) and "something's there but it's stale" (new).
      if (!selectedCityId.value || !cities.value.some((c) => c.id === selectedCityId.value)) {
        const fallbackId = demoCity.value?.id ?? cities.value[0]?.id ?? null
        selectedCityId.value = fallbackId
        if (fallbackId) localStorage.setItem(CITY_KEY, fallbackId)
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
