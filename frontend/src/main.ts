import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import './plugins/echarts'
import { vuetify } from './plugins/vuetify'
import router from './router'
import { initAnalytics } from './services/analytics'

import './style.css'

initAnalytics()

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(vuetify)

app.mount('#app')
