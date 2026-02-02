import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { Activity } from 'lucide-react'
import './LightCurve.css'

// Custom tooltip component - defined outside to avoid re-creation on each render
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  return (
    <div className="chart-tooltip">
      <div className="tooltip-header">Iteration {label}</div>
      {payload.map((p, i) => (
        <div key={i} className="tooltip-row" style={{ color: p.color }}>
          <span>{p.name}:</span>
          <span className="tooltip-value">
            {p.name === 'Confidence' ? `${(p.value * 100).toFixed(0)}%` : p.value.toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  )
}

function LightCurve({ candidate }) {
  const chartData = useMemo(() => {
    if (!candidate) return []

    // Check for history array (from Candidate model)
    const history = candidate.history || candidate.observations || []
    if (history.length === 0) return []

    return history.map((h, index) => ({
      iteration: h.iteration || index + 1,
      brightness: h.magnitude || h.brightness || h.flux || 0,
      confidence: h.confidence || candidate.confidence || 0,
      time: h.time || h.simulated_time || `T+${index}`,
    }))
  }, [candidate])

  return (
    <div className="light-curve">
      <div className="panel-header">
        <div className="panel-title">
          <Activity size={16} />
          <span>Light Curve</span>
        </div>
        {candidate && (
          <span className="candidate-badge">{candidate.id}</span>
        )}
      </div>

      <div className="chart-container">
        {!candidate ? (
          <div className="chart-placeholder">
            <Activity size={32} />
            <p>Select a candidate to view light curve</p>
          </div>
        ) : chartData.length === 0 ? (
          <div className="chart-placeholder">
            <Activity size={32} />
            <p>No observation history</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData}
              margin={{ top: 10, right: 20, left: 10, bottom: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(148, 163, 184, 0.1)"
              />
              <XAxis
                dataKey="iteration"
                stroke="#64748b"
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                axisLine={{ stroke: 'rgba(148, 163, 184, 0.2)' }}
              />
              <YAxis
                yAxisId="brightness"
                stroke="#64748b"
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                axisLine={{ stroke: 'rgba(148, 163, 184, 0.2)' }}
                label={{
                  value: 'Brightness',
                  angle: -90,
                  position: 'insideLeft',
                  style: { fontSize: 11, fill: '#94a3b8' }
                }}
              />
              <YAxis
                yAxisId="confidence"
                orientation="right"
                domain={[0, 1]}
                stroke="#64748b"
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                axisLine={{ stroke: 'rgba(148, 163, 184, 0.2)' }}
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                yAxisId="confidence"
                y={0.8}
                stroke="#10b981"
                strokeDasharray="5 5"
                label={{
                  value: 'Confirm threshold',
                  position: 'right',
                  style: { fontSize: 10, fill: '#10b981' }
                }}
              />
              <Line
                yAxisId="brightness"
                type="monotone"
                dataKey="brightness"
                name="Brightness"
                stroke="#6366f1"
                strokeWidth={2}
                dot={{ r: 3, fill: '#6366f1' }}
                activeDot={{ r: 5, fill: '#818cf8' }}
              />
              <Line
                yAxisId="confidence"
                type="stepAfter"
                dataKey="confidence"
                name="Confidence"
                stroke="#10b981"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={{ r: 3, fill: '#10b981' }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

export default LightCurve
