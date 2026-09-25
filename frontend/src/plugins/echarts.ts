/** Registers the ECharts building blocks used by the reusable chart shells.
 * Imported once (side-effect) from main.ts. */
import { BarChart, GaugeChart, LineChart, PieChart, RadarChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

// Session 019 — WOW #3 (Resilience Radar) needs both the `radar` series
// (RadarChart) and its own coordinate system (RadarComponent, the radar
// equivalent of GridComponent for cartesian charts) — registering only the
// series left the radar's axes/polygon with nothing to lay out on, so it
// silently rendered blank (caught in live Playwright verification).
use([
  CanvasRenderer,
  BarChart,
  LineChart,
  GaugeChart,
  PieChart,
  RadarChart,
  GridComponent,
  RadarComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
])
