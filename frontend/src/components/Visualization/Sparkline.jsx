import { useMemo } from 'react'

/**
 * Simple SVG Sparkline
 * @param {number[]} data - Array of values
 * @param {string} color - Stroke color
 * @param {number} width - SVG width
 * @param {number} height - SVG height
 */
function Sparkline({ data = [], color = 'currentColor', width = 100, height = 30 }) {
  const points = useMemo(() => {
    if (!data || data.length < 2) return ''

    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const stepX = width / (data.length - 1)

    return data
      .map((val, i) => {
        const x = i * stepX
        const y = height - ((val - min) / range) * height
        return `${x},${y}`
      })
      .join(' ')
  }, [data, width, height])

  if (!data || data.length < 2) return null

  return (
    <svg width={width} height={height} className="sparkline" overflow="visible">
      {/* Glow effect */}
      <defs>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ filter: 'drop-shadow(0 0 2px rgba(0,0,0,0.5))' }}
      />
      {/* Fill area (optional, maybe later) */}
    </svg>
  )
}

export default Sparkline
