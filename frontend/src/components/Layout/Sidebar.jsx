import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  History,
  Settings as SettingsIcon,
  Play,
  Pause,
  Square,
  Cloud,
  Eye,
  Target,
  TrendingUp,
  ChevronRight,
} from 'lucide-react'
import './Sidebar.css'

// Load saved config from localStorage
function getMarathonConfig() {
  const defaults = {
    max_iterations: 16,
    num_stars: 100,
    num_transients: 2,
    inject_false_positives: true,
    step_interval_hours: 0.5,
  }
  try {
    const saved = localStorage.getItem('sentinel-config')
    if (saved) {
      return { ...defaults, ...JSON.parse(saved) }
    }
  } catch {
    // Invalid JSON, use defaults
  }
  return defaults
}

function Sidebar({ marathonState, contextState, onStart, onStop, onPause }) {
  const { isRunning, isPaused } = marathonState

  const handleStart = () => {
    // Load fresh config from localStorage at start time
    const config = getMarathonConfig()
    onStart(config)
  }

  // Get weather data from context
  const weather = contextState?.weather || { seeing: 0, cloud_extinction: 0, observability: 'UNKNOWN' }
  const candidates = contextState?.candidates || []
  const activeCandidates = candidates.filter(c => c.status !== 'REJECTED')
  const confirmedCandidates = candidates.filter(c => c.status === 'CONFIRMED')

  const getObservabilityColor = (obs) => {
    switch (obs) {
      case 'EXCELLENT': return 'var(--weather-excellent)'
      case 'GOOD': return 'var(--weather-good)'
      case 'POOR': return 'var(--weather-poor)'
      case 'UNUSABLE': return 'var(--weather-unusable)'
      default: return 'var(--text-muted)'
    }
  }

  return (
    <aside className="sidebar">
      {/* Navigation */}
      <nav className="sidebar-nav">
        <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <LayoutDashboard size={18} />
          <span>Dashboard</span>
        </NavLink>
        <NavLink to="/playback" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <History size={18} />
          <span>Playback</span>
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <SettingsIcon size={18} />
          <span>Settings</span>
        </NavLink>
      </nav>

      {/* Marathon Controls */}
      <div className="sidebar-section">
        <div className="section-header">
          <Target size={14} />
          <span>Marathon Control</span>
        </div>
        <div className="control-buttons">
          {!isRunning ? (
            <button className="btn btn-primary control-btn" onClick={handleStart}>
              <Play size={16} />
              Start Marathon
            </button>
          ) : (
            <>
              <button className="btn btn-secondary control-btn" onClick={onPause}>
                {isPaused ? <Play size={16} /> : <Pause size={16} />}
                {isPaused ? 'Resume' : 'Pause'}
              </button>
              <button className="btn btn-danger control-btn" onClick={onStop}>
                <Square size={16} />
                Stop
              </button>
            </>
          )}
        </div>
      </div>

      {/* Weather Widget */}
      <div className="sidebar-section">
        <div className="section-header">
          <Cloud size={14} />
          <span>Weather Conditions</span>
        </div>
        <div className="weather-widget">
          <div className="weather-stat">
            <span className="weather-label">Seeing</span>
            <span className="weather-value">{weather.seeing?.toFixed(2) || '—'}"</span>
          </div>
          <div className="weather-stat">
            <span className="weather-label">Clouds</span>
            <span className="weather-value">
              {weather.cloud_extinction ? `${(weather.cloud_extinction * 100).toFixed(0)}%` : '—'}
            </span>
          </div>
          <div className="weather-observability">
            <Eye size={14} />
            <span style={{ color: getObservabilityColor(weather.observability) }}>
              {weather.observability || 'UNKNOWN'}
            </span>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="sidebar-section">
        <div className="section-header">
          <TrendingUp size={14} />
          <span>Detection Stats</span>
        </div>
        <div className="stats-grid">
          <div className="stat-item">
            <span className="stat-value">{activeCandidates.length}</span>
            <span className="stat-label">Active</span>
          </div>
          <div className="stat-item">
            <span className="stat-value text-success">{confirmedCandidates.length}</span>
            <span className="stat-label">Confirmed</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{contextState?.alerts_triggered || 0}</span>
            <span className="stat-label">Alerts</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{contextState?.total_observations || 0}</span>
            <span className="stat-label">Observations</span>
          </div>
        </div>
      </div>

      {/* Candidate Quick View */}
      {activeCandidates.length > 0 && (
        <div className="sidebar-section">
          <div className="section-header">
            <span>Active Candidates</span>
            <ChevronRight size={14} />
          </div>
          <div className="candidates-quick">
            {activeCandidates.slice(0, 5).map(candidate => (
              <div key={candidate.id} className="candidate-quick-item">
                <span className={`badge badge-${candidate.status.toLowerCase()}`}>
                  {candidate.id}
                </span>
                <span className="candidate-confidence">
                  {(candidate.confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}

export default Sidebar
