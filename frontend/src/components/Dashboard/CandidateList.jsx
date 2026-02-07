import { List, MapPin, TrendingUp, AlertCircle, Bell, Sun } from 'lucide-react'
import './CandidateList.css'

function CandidateList({ candidates, selectedCandidate, onSelectCandidate }) {
  const sortedCandidates = [...candidates].sort((a, b) => {
    // Sort by status priority, then confidence
    const statusPriority = { ALERTED: 0, BRIGHTENING: 1, MONITORING: 2, NEW: 3, REJECTED: 4 }
    const priorityDiff = statusPriority[a.status] - statusPriority[b.status]
    if (priorityDiff !== 0) return priorityDiff
    return b.confidence - a.confidence
  })

  const getStatusIcon = (status) => {
    switch (status) {
      case 'ALERTED':
        return <Bell size={14} className="status-icon alerted" />
      case 'BRIGHTENING':
        return <Sun size={14} className="status-icon brightening" />
      case 'MONITORING':
        return <TrendingUp size={14} className="status-icon monitoring" />
      case 'NEW':
        return <MapPin size={14} className="status-icon new" />
      default:
        return null
    }
  }

  return (
    <div className="candidate-list">
      <div className="panel-header">
        <div className="panel-title">
          <List size={16} />
          <span>Candidates</span>
        </div>
        <span className="candidate-count">{candidates.length}</span>
      </div>

      <div className="candidates-container">
        {sortedCandidates.length === 0 ? (
          <div className="candidates-placeholder">
            <MapPin size={32} />
            <p>No candidates detected</p>
          </div>
        ) : (
          sortedCandidates.map(candidate => (
            <div
              key={candidate.id}
              className={`candidate-item ${selectedCandidate?.id === candidate.id ? 'selected' : ''} ${candidate.status.toLowerCase()}`}
              onClick={() => onSelectCandidate(candidate)}
            >
              <div className="candidate-main">
                <div className="candidate-id-row">
                  {getStatusIcon(candidate.status)}
                  <span className="candidate-id">{candidate.id}</span>
                  <span className={`badge badge-${candidate.status.toLowerCase()}`}>
                    {candidate.status}
                  </span>
                </div>
                <div className="candidate-details">
                  <span className="candidate-coords">
                    ({candidate.x}, {candidate.y})
                  </span>
                  <span className="candidate-hypothesis">
                    {candidate.hypothesis || 'Unknown'}
                  </span>
                </div>
              </div>

              <div className="candidate-stats">
                <div className="stat-bar">
                  <div className="stat-label">Confidence</div>
                  <div className="confidence-bar">
                    <div
                      className="confidence-fill"
                      style={{ width: `${candidate.confidence * 100}%` }}
                    />
                  </div>
                  <span className="confidence-value">
                    {(candidate.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="observations-count">
                  {candidate.history?.length || 0} observations
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default CandidateList
