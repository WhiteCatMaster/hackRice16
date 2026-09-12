// The hero element: the projected balance, day by day, to the flight home.
//
// Every point is P2's forecast series — nothing here is drawn by hand. When the
// line crosses zero before the target date, that crossing is the runway date and
// the whole product exists to move it to the right.
//
// The geometry is the web chart's, with one change forced by the phone. The web
// SVG is `preserveAspectRatio="none"`, stretched to whatever width the panel
// has; stretching non-uniformly on a 390pt screen thins the stroke to nothing
// and squashes the runway marker, so this one measures its container and draws
// at real pixel size instead.

import { useState } from 'react'
import { StyleSheet, Text, View, type LayoutChangeEvent } from 'react-native'
import Svg, { Circle, Defs, Line, LinearGradient, Path, Stop } from 'react-native-svg'

import type { Forecast } from '../lib/contract'
import { dayMonth, moneyRound } from '../lib/format'
import { color, font, text } from '../lib/theme'

const H = 190
const TOP = 12
const BOTTOM = 20
/** Room for the y-axis figures, which sit outside the plot on the web too. */
const GUTTER = 52

interface Props {
  forecast: Forecast
  /** Multiply every dollar figure by this to show the home currency. */
  rate: number
  currency: string
  labelCount?: number
}

export function ForecastChart({ forecast, rate, currency, labelCount = 4 }: Props) {
  const [width, setWidth] = useState(0)

  const series = forecast.series
  if (series.length < 2) return null

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)

  const values = series.map((p) => p.balance * rate)
  const max = Math.max(...values, 0)
  const min = Math.min(...values, 0)
  const span = max - min || 1
  const ticks = [max, max - span / 3, max - (2 * span) / 3, min]

  const labelStep = Math.max(1, Math.floor((series.length - 1) / Math.max(1, labelCount - 1)))
  const labels = series.filter((_, i) => i % labelStep === 0 || i === series.length - 1)

  // Nothing to draw until the first layout pass reports a width. Reserve the
  // height so the panel does not jump when the line arrives a frame later.
  const W = Math.max(0, width)
  const plot = (
    <View style={styles.plot} onLayout={onLayout}>
      {W > 0 && <Plot forecast={forecast} values={values} W={W} max={max} min={min} span={span} />}
    </View>
  )

  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <View style={styles.axis}>
          {ticks.map((t, i) => (
            <Text key={i} style={styles.axisLabel} numberOfLines={1}>
              {moneyRound(t, currency)}
            </Text>
          ))}
        </View>
        {plot}
      </View>

      <View style={[styles.dates, { marginLeft: GUTTER }]}>
        {labels.map((p) => (
          <Text key={p.date} style={styles.axisLabel}>
            {dayMonth(p.date)}
          </Text>
        ))}
      </View>

      {forecast.runway_date && (
        <View style={styles.callout}>
          <View style={styles.calloutDot} />
          <Text style={styles.calloutText}>Runway ends </Text>
          <Text style={styles.calloutDate}>{dayMonth(forecast.runway_date)}</Text>
        </View>
      )}
    </View>
  )
}

function Plot({
  forecast,
  values,
  W,
  max,
  span,
}: {
  forecast: Forecast
  values: number[]
  W: number
  max: number
  min: number
  span: number
}) {
  const series = forecast.series
  const x = (i: number) => (i / (series.length - 1)) * W
  const y = (value: number) => TOP + ((max - value) / span) * (H - TOP - BOTTOM)

  const line = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
    .join(' ')
  const area = `${line} L ${W.toFixed(1)} ${H} L 0 ${H} Z`
  const zeroY = y(0)
  const ticks = [max, max - span / 3, max - (2 * span) / 3]

  const runwayIndex = forecast.runway_date
    ? series.findIndex((p) => p.date >= forecast.runway_date!)
    : -1

  return (
    <Svg
      width={W}
      height={H}
      accessibilityRole="image"
      accessibilityLabel={
        forecast.runway_date
          ? `Projected balance falls below zero on ${forecast.runway_date}, before the flight home on ${forecast.target}`
          : `Projected balance stays positive through ${forecast.target}`
      }
    >
      <Defs>
        <LinearGradient id="forecastArea" x1="0" x2="0" y1="0" y2="1">
          <Stop offset="0%" stopColor={color.teal} stopOpacity="0.24" />
          <Stop offset="100%" stopColor={color.teal} stopOpacity="0" />
        </LinearGradient>
      </Defs>

      {ticks.slice(1).map((t, i) => (
        <Line
          key={i}
          x1="0"
          y1={y(t)}
          x2={W}
          y2={y(t)}
          stroke={color.lineSoft}
          strokeDasharray="4 5"
        />
      ))}
      <Line x1="0" y1={zeroY} x2={W} y2={zeroY} stroke={color.line} />

      <Path d={area} fill="url(#forecastArea)" />
      <Path d={line} fill="none" stroke={color.teal} strokeWidth={2.5} strokeLinejoin="round" />

      {runwayIndex >= 0 && (
        <>
          <Line
            x1={x(runwayIndex)}
            y1={TOP}
            x2={x(runwayIndex)}
            y2={H - BOTTOM + 10}
            stroke={color.flag}
            strokeDasharray="4 4"
          />
          <Circle
            cx={x(runwayIndex)}
            cy={y(values[runwayIndex])}
            r={4.5}
            fill={color.surface}
            stroke={color.flag}
            strokeWidth={2.5}
          />
        </>
      )}

      <Circle
        cx={W - 2}
        cy={y(values[values.length - 1])}
        r={4.5}
        fill={color.surface}
        stroke={color.teal}
        strokeWidth={2.5}
      />
    </Svg>
  )
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  row: { flexDirection: 'row', alignItems: 'stretch' },
  axis: {
    width: GUTTER,
    height: H,
    paddingRight: 8,
    paddingTop: TOP,
    paddingBottom: BOTTOM,
    justifyContent: 'space-between',
    alignItems: 'flex-end',
  },
  plot: { flex: 1, height: H },
  axisLabel: {
    fontFamily: font.figure,
    fontSize: 9,
    color: color.inkFaint,
    fontVariant: ['tabular-nums'],
  },
  dates: { flexDirection: 'row', justifyContent: 'space-between' },
  callout: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  calloutDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: color.flag },
  calloutText: { ...text.small, color: color.flagDeep },
  calloutDate: { fontFamily: font.figureSemi, fontSize: 11, color: color.flagDeep },
})
