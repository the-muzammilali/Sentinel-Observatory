import { Clock } from 'lucide-react'
import './Timeline.css'

function Timeline({ iterations, currentIteration }) {
  const maxIterations = Math.max(iterations.length, 16)

  const getIterationClass = (iter) => {
    if (iter.iteration === currentIteration) return 'current'
    if (iter.weather?.observability === 'UNUSABLE') return 'unusable'
    if (iter.num_candidates > 0) return 'active'
    return 'normal'
  }

  return (
    <div className="timeline">
      <div className="timeline-header">
        <div className="timeline-title">
          <Clock size={14} />
          <span>Observation Timeline</span>
        </div>
        <span className="timeline-info">
          {iterations.length} / {maxIterations} iterations
        </span>
      </div>

      <div className="timeline-track">
        {Array.from({ length: maxIterations }, (_, i) => {
          const iter = iterations.find(it => it.iteration === i + 1)
          return (
            <div
              key={i}
              className={`timeline-point ${iter ? getIterationClass(iter) : 'pending'}`}
              title={iter ? `Iteration ${iter.iteration}: ${iter.num_candidates} candidates` : `Iteration ${i + 1}`}
            >
              <div className="point-marker" />
              {iter?.num_candidates > 0 && (
                <div className="point-indicator">{iter.num_candidates}</div>
              )}
            </div>
          )
        })}
      </div>

      <div className="timeline-labels">
        <span>Start</span>
        <span>End</span>
      </div>
    </div>
  )
}

export default Timeline
