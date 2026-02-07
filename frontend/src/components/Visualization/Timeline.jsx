import { Clock } from 'lucide-react'
import './Timeline.css'

function Timeline({ iterations, currentIteration, totalIterations }) {
  const maxIterations = totalIterations || Math.max(iterations.length, 16)

  const getIterationClass = (iter) => {
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
        <div className="timeline-progress-bg">
          <div 
            className="timeline-progress-fill" 
            style={{ width: `${Math.min((currentIteration / maxIterations) * 100, 100)}%` }}
          />
        </div>
        
        {/* Render markers for interesting iterations only to avoid clutter */}
        {iterations.map((iter) => {
          // Only show markers for active (candidates found) or unusable (bad weather) iterations
          // Or the current one if it's not the last one
          const isInteresting = iter.num_candidates > 0 || iter.weather?.observability === 'UNUSABLE'
          
          if (!isInteresting) return null

          const position = (iter.iteration / maxIterations) * 100
          
          return (
            <div
              key={iter.iteration}
              className={`timeline-marker ${getIterationClass(iter)}`}
              style={{ left: `${position}%` }}
              title={`Iteration ${iter.iteration}: ${iter.num_candidates} candidates`}
            >
              {iter.num_candidates > 0 && (
                <div className="marker-indicator">{iter.num_candidates}</div>
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
