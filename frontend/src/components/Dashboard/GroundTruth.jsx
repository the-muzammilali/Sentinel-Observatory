import { useState, useEffect } from 'react'
import { CheckCircle2, XCircle, Target, Percent } from 'lucide-react'
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

  useEffect(() => {
    if (!marathonState.isRunning && marathonState.status !== 'completed') return

    const fetchMetrics = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/ground-truth')
        if (response.ok) {
          const data = await response.json()
          setMetrics(data)
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
          <span>Ground Truth</span>
        </div>
      </div>

      <div className="metrics-container">
        {/* Main metrics */}
        <div className="main-metrics">
          <div className={`metric-card ${getScoreClass(metrics.f1_score)}`}>
            <div className="metric-value">{(metrics.f1_score * 100).toFixed(0)}%</div>
            <div className="metric-label">F1 Score</div>
          </div>
        </div>

        <div className="secondary-metrics">
          <div className="metric-row">
            <span className="metric-name">Precision</span>
            <div className="metric-bar">
              <div
                className="metric-fill precision"
                style={{ width: `${metrics.precision * 100}%` }}
              />
            </div>
            <span className="metric-percent">{(metrics.precision * 100).toFixed(0)}%</span>
          </div>

          <div className="metric-row">
            <span className="metric-name">Recall</span>
            <div className="metric-bar">
              <div
                className="metric-fill recall"
                style={{ width: `${metrics.recall * 100}%` }}
              />
            </div>
            <span className="metric-percent">{(metrics.recall * 100).toFixed(0)}%</span>
          </div>
        </div>

        {/* Confusion matrix summary */}
        <div className="confusion-summary">
          <div className="confusion-item positive">
            <CheckCircle2 size={14} />
            <span>TP: {metrics.true_positives}</span>
          </div>
          <div className="confusion-item fp">
            <XCircle size={14} />
            <span>FP: {metrics.false_positives}</span>
          </div>
          <div className="confusion-item fn">
            <XCircle size={14} />
            <span>FN: {metrics.false_negatives}</span>
          </div>
        </div>

        {/* Detection progress */}
        <div className="detection-progress">
          <div className="progress-label">
            <Target size={12} />
            <span>Detection Progress</span>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: metrics.total_transients > 0
                  ? `${(metrics.detected_transients / metrics.total_transients) * 100}%`
                  : '0%'
              }}
            />
          </div>
          <span className="progress-text">
            {metrics.detected_transients} / {metrics.total_transients} transients
          </span>
        </div>
      </div>
    </div>
  )
}

export default GroundTruth
