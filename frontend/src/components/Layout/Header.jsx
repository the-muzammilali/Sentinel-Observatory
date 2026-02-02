import { Telescope, Wifi, WifiOff, Zap } from 'lucide-react'
import './Header.css'

function Header({ marathonState, wsConnected }) {
  const { isRunning, currentIteration, maxIterations, status } = marathonState

  const getStatusLabel = () => {
    switch (status) {
      case 'running':
        return 'LIVE'
      case 'paused':
        return 'PAUSED'
      case 'completed':
        return 'COMPLETED'
      case 'error':
        return 'ERROR'
      default:
        return 'OFFLINE'
    }
  }

  const getStatusClass = () => {
    switch (status) {
      case 'running':
        return 'status-live'
      case 'paused':
        return 'status-paused'
      case 'completed':
        return 'status-completed'
      case 'error':
        return 'status-error'
      default:
        return 'status-offline'
    }
  }

  return (
    <header className="header">
      <div className="header-left">
        <div className="header-logo">
          <Telescope size={28} className="logo-icon" />
          <div className="logo-text">
            <span className="logo-title">SENTINEL</span>
            <span className="logo-subtitle">OBSERVATORY</span>
          </div>
        </div>
      </div>

      <div className="header-center">
        {isRunning && (
          <div className="iteration-display animate-fade-in">
            <Zap size={16} className="iteration-icon" />
            <span className="iteration-label">Iteration</span>
            <span className="iteration-value">
              {currentIteration} / {maxIterations}
            </span>
          </div>
        )}
      </div>

      <div className="header-right">
        <div className={`status-indicator ${getStatusClass()}`}>
          {status === 'running' && <span className="pulse-dot" />}
          <span className="status-label">{getStatusLabel()}</span>
        </div>

        <div className={`connection-indicator ${wsConnected ? 'connected' : 'disconnected'}`}>
          {wsConnected ? (
            <>
              <Wifi size={16} />
              <span>Connected</span>
            </>
          ) : (
            <>
              <WifiOff size={16} />
              <span>Disconnected</span>
            </>
          )}
        </div>
      </div>
    </header>
  )
}

export default Header
