import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchCities } from '@/services/geographyApi'
import type { City } from '@/types'

const CITY_KEY = 'aquaresilience.city_id'

export const useCityStore = defineStore('city', () => {
  const cities = ref<City[]>([])
  const selectedCityId = ref<string | null>(localStorage.getItem(CITY_KEY))
  const loaded = ref(false)

  const selectedCity = computed<City | null>(() => {
    if (!cities.value.length) return null
    return cities.value.find((c) => c.id === selectedCityId.value) ?? demoCity.value ?? cities.value[0]
  })

  const demoCity = computed<City | null>(
    () => cities.value.find((c) => c.has_live_data && c.label_en === 'Toulouse') ?? cities.value.find((c) => c.has_live_data) ?? null,
  )

  async function load(): Promise<void> {
    if (loaded.value) return
    try {
      cities.value = await fetchCities()
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
