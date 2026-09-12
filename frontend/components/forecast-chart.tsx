'use client'

import type { Forecast } from '@/lib/contract'
import { dayMonth, moneyRound } from '@/lib/format'

const W = 720
const H = 245
const TOP = 14
const BOTTOM = 30

interface Props {
  forecast: Forecast
  /** Multiply every dollar figure by this to show the home currency. */
  rate: number
  currency: string
  labelCount?: number
}

/**
 * The hero element: the projected balance, day by day, to the flight home.
 *
 * Every point is P2's forecast series — nothing here is drawn by hand. When the
 * line crosses zero before the target date, that crossing is the runway date and
 * the whole product exists to move it to the right.
 */
export function ForecastChart({ forecast, rate, currency, labelCount = 5 }: Props) {
  const series = forecast.series
  if (series.length < 2) return null

  const values = series.map((p) => p.balance * rate)
  const max = Math.max(...values, 0)
  const min = Math.min(...values, 0)
  const span = max - min || 1

  const x = (i: number) => (i / (series.length - 1)) * W
  const y = (value: number) => TOP + ((max - value) / span) * (H - TOP - BOTTOM)

  const line = values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L ${W} ${H} L 0 ${H} Z`
  const zeroY = y(0)

  const runwayIndex = forecast.runway_date
    ? series.findIndex((p) => p.date >= forecast.runway_date!)
    : -1

  const ticks = [max, max - span / 3, max - (2 * span) / 3, min]

  const labelStep = Math.max(1, Math.floor((series.length - 1) / (labelCount - 1)))
  const labels = series.filter((_, i) => i % labelStep === 0 || i === series.length - 1)

  return (
    <div className="chart-wrap">
      <div className="chart-y">
        {ticks.map((t, i) => (
          <span key={i}>{moneyRound(t, currency)}</span>
        ))}
      </div>
      <svg
        className="forecast-chart"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={
          forecast.runway_date
            ? `Projected balance falls below zero on ${forecast.runway_date}, before the flight home on ${forecast.target}`
            : `Projected balance stays positive through ${forecast.target}`
        }
      >
        <defs>
          <linearGradient id="forecast-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#3a674f" stopOpacity=".28" />
            <stop offset="100%" stopColor="#3a674f" stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticks.slice(1, -1).map((t, i) => (
          <line key={i} x1="0" y1={y(t)} x2={W} y2={y(t)} stroke="#ecd9d2" strokeDasharray="4 5" />
        ))}
        <line x1="0" y1={zeroY} x2={W} y2={zeroY} stroke="#dec0b7" />

        <path d={area} fill="url(#forecast-area)" />
        <path d={line} fill="none" stroke="#3a674f" strokeWidth="3" vectorEffect="non-scaling-stroke" />

        {runwayIndex >= 0 && (
          <g>
            <line
              x1={x(runwayIndex)}
              y1={TOP}
              x2={x(runwayIndex)}
              y2={H - BOTTOM + 12}
              stroke="#9f3c16"
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
            />
            <circle
              cx={x(runwayIndex)}
              cy={y(values[runwayIndex])}
              r="5"
              fill="#fffdf9"
              stroke="#9f3c16"
              strokeWidth="3"
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )}
        <circle
          cx={W}
          cy={y(values[values.length - 1])}
          r="5"
          fill="#fffdf9"
          stroke="#3a674f"
          strokeWidth="3"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <div className="chart-labels">
        {labels.map((p) => (
          <span key={p.date}>{dayMonth(p.date)}</span>
        ))}
      </div>

      {forecast.runway_date && (
        <div className="chart-callout">
          <span className="callout-dot" /> Runway ends here
          <strong>{dayMonth(forecast.runway_date)}</strong>
        </div>
      )}
    </div>
  )
}
