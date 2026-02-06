import { useState, useEffect } from 'react'
import { CheckCircle2, XCircle, Target } from 'lucide-react'
import Sparkline from '../Visualization/Sparkline'
import './GroundTruth.css'

function GroundTruth({ marathonState }) {
  const [metrics, setMetrics] = useState({
    precision: 0,
    recall: 0,
    f1_score: 0,
    true_positives: 0,
    false_positives: 0,
    false_negatives: 0,
    total_transients: 0,
    detected_transients: 0,
  })

  // Simulated history for sparklines
  const [history, setHistory] = useState({
    f1: [0.7, 0.72, 0.75, 0.74, 0.78, 0.82, 0.85, 0.88],
    precision: [0.65, 0.68, 0.7, 0.72, 0.75, 0.79, 0.82, 0.85],
    recall: [0.6, 0.65, 0.68, 0.7, 0.72, 0.75, 0.78, 0.8]
  })

  useEffect(() => {
    if (!marathonState.isRunning && marathonState.status !== 'completed') return

    const fetchMetrics = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/ground-truth')
        if (response.ok) {
          const data = await response.json()
          setMetrics(data)
          
          // Update history directly here to avoid cascading effect warning
          setHistory(prev => ({
            f1: [...prev.f1.slice(1), data.f1_score || 0],
            precision: [...prev.precision.slice(1), data.precision || 0],
            recall: [...prev.recall.slice(1), data.recall || 0]
          }))
        }
      } catch (error) {
        console.error('Failed to fetch ground truth:', error)
      }
    }

    fetchMetrics()
    const interval = setInterval(fetchMetrics, 5000)
    return () => clearInterval(interval)
  }, [marathonState.isRunning, marathonState.status])

  const getScoreClass = (score) => {
    if (score >= 0.8) return 'excellent'
    if (score >= 0.6) return 'good'
    if (score >= 0.4) return 'fair'
    return 'poor'
  }

  return (
    <div className="ground-truth">
      <div className="panel-header">
        <div className="panel-title">
          <Target size={16} />
          <span>Telemetry</span>
        </div>
      </div>

      <div className="telemetry-list">
        {/* F1 Score Row */}
        <div className="telemetry-row">
          <div className="telemetry-info">
            <span className="telemetry-label">F1 Score</span>
            <span className={`telemetry-value ${getScoreClass(metrics.f1_score)}`}>
              {(metrics.f1_score * 100).toFixed(0)}%
            </span>
          </div>
          <div className="telemetry-chart">
            <Sparkline data={history.f1} color="var(--accent-primary)" />
          </div>
        </div>

        {/* Precision Row */}
        <div className="telemetry-row">
          <div className="telemetry-info">
            <span className="telemetry-label">Precision</span>
            <span className="telemetry-value">
              {(metrics.precision * 100).toFixed(0)}%
            </span>
          </div>
          <div className="telemetry-chart">
            <Sparkline data={history.precision} color="var(--accent-info)" />
          </div>
        </div>

        {/* Recall Row */}
        <div className="telemetry-row">
          <div className="telemetry-info">
            <span className="telemetry-label">Recall</span>
            <span className="telemetry-value">
              {(metrics.recall * 100).toFixed(0)}%
            </span>
          </div>
          <div className="telemetry-chart">
            <Sparkline data={history.recall} color="var(--accent-warning)" />
          </div>
        </div>

        {/* Transient Progress (Mini Bar) */}
        <div className="telemetry-row">
             <div className="telemetry-info">
            <span className="telemetry-label">Detection</span>
            <span className="telemetry-value text-muted">
               {metrics.detected_transients}/{metrics.total_transients}
            </span>
          </div>
          <div className="telemetry-bar-container">
            <div className="telemetry-bar-bg">
                <div 
                    className="telemetry-bar-fill"
                    style={{ 
                        width: metrics.total_transients > 0 
                            ? `${(metrics.detected_transients / metrics.total_transients) * 100}%` 
                            : '0%' 
                    }}
                />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default GroundTruth
