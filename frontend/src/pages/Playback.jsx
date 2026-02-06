import { useState, useEffect, useRef, useCallback } from 'react'
import {
  History,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronLeft,
  ChevronRight,
  Calendar,
  Clock,
  Target,
  Cloud,
  Eye,
  Brain,
  AlertTriangle,
  List,
  X,
  ZoomIn,
  ZoomOut,
  Move,
  RefreshCw,
} from 'lucide-react'
import './Playback.css'

function Playback() {
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState(null)
  const [currentIteration, setCurrentIteration] = useState(1)
  const [iterationData, setIterationData] = useState(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  
  // Image preloading for instant switching
  const [preloadedImages, setPreloadedImages] = useState({})
  const currentImageRef = useRef(null)
  const containerRef = useRef(null)
  
  // Zoom and pan state
  const [zoom, setZoom] = useState(1)
  const [panMode, setPanMode] = useState(false)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 })

  // Fetch saved sessions
  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/sessions')
        if (response.ok) {
          const data = await response.json()
          setSessions(data.sessions || [])
        }
      } catch (error) {
        console.error('Failed to fetch sessions:', error)
      }
    }
    fetchSessions()
  }, [])

  // Fetch iteration data when iteration changes (no loading state for smooth transitions)
  useEffect(() => {
    if (!selectedSession || !currentIteration) return

    const fetchIterationData = async () => {
      try {
        const response = await fetch(
          `http://localhost:8000/api/sessions/${selectedSession.session_id}/iterations/${currentIteration}`
        )
        if (response.ok) {
          const data = await response.json()
          setIterationData(data)
        }
      } catch (error) {
        console.error('Failed to fetch iteration data:', error)
      }
    }
    fetchIterationData()
  }, [selectedSession, currentIteration])

  // Preload all session images when session is selected
  useEffect(() => {
    if (!selectedSession) return

    const preloadAllImages = async () => {
      const images = {}
      for (let i = 1; i <= selectedSession.total_iterations; i++) {
        const url = `http://localhost:8000/api/sessions/${selectedSession.session_id}/iterations/${i}/image`
        const img = new Image()
        img.src = url
        images[i] = url
      }
      setPreloadedImages(images)
    }
    preloadAllImages()
  }, [selectedSession])

  // Get current image URL from preloaded cache
  const currentImageUrl = selectedSession ? 
    preloadedImages[currentIteration] || 
    `http://localhost:8000/api/sessions/${selectedSession.session_id}/iterations/${currentIteration}/image` 
    : null

  // Auto-advance playback
  useEffect(() => {
    if (!isPlaying || !selectedSession) return

    const interval = setInterval(() => {
      setCurrentIteration(prev => {
        if (prev >= selectedSession.total_iterations) {
          setIsPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, 2000 / playbackSpeed)

    return () => clearInterval(interval)
  }, [isPlaying, selectedSession, playbackSpeed])

  const handleSelectSession = useCallback((session) => {
    setSelectedSession(session)
    setCurrentIteration(1)
    setIsPlaying(false)
    setIterationData(null)
    setPreloadedImages({})
  }, [])

  const handlePlayPause = useCallback(() => setIsPlaying(p => !p), [])
  
  const handlePrev = useCallback(() => {
    setCurrentIteration(prev => Math.max(1, prev - 1))
  }, [])
  
  const handleNext = useCallback(() => {
    if (selectedSession) {
      setCurrentIteration(prev => Math.min(selectedSession.total_iterations, prev + 1))
    }
  }, [selectedSession])

  const handleSliderChange = useCallback((e) => {
    setCurrentIteration(Number(e.target.value))
    setIsPlaying(false)
  }, [])

  // Zoom and pan handlers
  const handleZoomIn = useCallback(() => setZoom(prev => Math.min(prev + 0.5, 4)), [])
  const handleZoomOut = useCallback(() => setZoom(prev => Math.max(prev - 0.5, 0.5)), [])
  const handleResetView = useCallback(() => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
    setPanMode(false)
  }, [])
  const togglePanMode = useCallback(() => setPanMode(prev => !prev), [])

  // Mouse event handlers for pan mode
  const handleMouseDown = useCallback((e) => {
    if (!panMode) return
    e.preventDefault()
    setIsDragging(true)
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: pan.x,
      panY: pan.y
    }
  }, [panMode, pan])

  const handleMouseMove = useCallback((e) => {
    if (!isDragging) return
    const dx = e.clientX - dragStartRef.current.x
    const dy = e.clientY - dragStartRef.current.y
    const maxPan = Math.max(100, (zoom - 1) * 200 + 100)
    setPan({
      x: Math.max(-maxPan, Math.min(maxPan, dragStartRef.current.panX + dx)),
      y: Math.max(-maxPan, Math.min(maxPan, dragStartRef.current.panY + dy))
    })
  }, [isDragging, zoom])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  // Global mouse event listeners for pan
  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
      return () => {
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [isDragging, handleMouseMove, handleMouseUp])

  const formatDate = (dateStr) => {
    try {
      return new Date(dateStr).toLocaleString()
    } catch {
      return dateStr
    }
  }

  const getStatusColor = (status) => {
    switch (status?.toUpperCase()) {
      case 'CONFIRMED': return 'var(--accent-success)'
      case 'REJECTED': return 'var(--accent-error)'
      case 'PENDING': return 'var(--accent-warning)'
      default: return 'var(--text-muted)'
    }
  }

  // No session selected - show session picker
  if (!selectedSession) {
    return (
      <div className="playback-page" ref={containerRef}>
        <div className="playback-header">
          <h1><History size={24} /> Marathon Playback</h1>
          <p>Select a recorded session to replay</p>
        </div>
        
        <div className="session-grid">
          {sessions.length === 0 ? (
            <div className="empty-state-large">
              <History size={64} />
              <h2>No Recorded Sessions</h2>
              <p>Run a marathon from the Dashboard to create recordings</p>
            </div>
          ) : (
            sessions.map(session => (
              <div
                key={session.session_id}
                className="session-card"
                onClick={() => handleSelectSession(session)}
              >
                <div className="session-card-header">
                  <Calendar size={16} />
                  <span>{formatDate(session.start_time)}</span>
                </div>
                <div className="session-card-stats">
                  <div className="stat">
                    <Clock size={14} />
                    <span>{session.total_iterations} iterations</span>
                  </div>
                  <div className="stat">
                    <Target size={14} />
                    <span>{session.confirmed_count || 0} confirmed</span>
                  </div>
                </div>
                <button className="btn btn-primary session-play-btn">
                  <Play size={16} /> Replay Session
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    )
  }

  // Session selected - show dashboard-like playback view
  return (
    <div className="playback-dashboard" ref={containerRef}>
      {/* Top row: Telescope View + Data Panels */}
      <div className="playback-row playback-row-main">
        {/* Telescope Panel */}
        <div className="playback-panel telescope-panel">
          <div
            className={`telescope-content ${panMode ? 'pan-mode' : ''} ${isDragging ? 'is-dragging' : ''}`}
            onMouseDown={handleMouseDown}
          >
            {/* Left side controls */}
            <div className="side-controls left-controls">
              <span className="iteration-badge-side">
                {currentIteration}/{selectedSession.total_iterations}
              </span>
            </div>

            {/* Right side controls */}
            <div className="side-controls right-controls">
              <button className="btn btn-icon side-btn" onClick={handleZoomIn} title="Zoom in">
                <ZoomIn size={18} />
              </button>
              <span className="zoom-level-vertical">{(zoom * 100).toFixed(0)}%</span>
              <button className="btn btn-icon side-btn" onClick={handleZoomOut} title="Zoom out">
                <ZoomOut size={18} />
              </button>
              <div className="controls-divider"></div>
              <button 
                className={`btn btn-icon side-btn ${panMode ? 'active' : ''}`}
                onClick={togglePanMode}
                title={panMode ? 'Exit pan mode' : 'Enter pan mode'}
              >
                <Move size={18} />
              </button>
              <button className="btn btn-icon side-btn" onClick={handleResetView} title="Reset view">
                <RefreshCw size={18} />
              </button>
            </div>

            {currentImageUrl ? (
              <div
                className="image-container"
                style={{
                  transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
                }}
              >
                <img
                  ref={currentImageRef}
                  src={currentImageUrl}
                  alt={`Iteration ${currentIteration}`}
                  className="telescope-image"
                  draggable={false}
                />
              </div>
            ) : (
              <div className="no-image">No image available</div>
            )}

            {/* Bottom info bar */}
            <div className="telescope-info-bar">
              <Eye size={14} />
              <span className="info-label">Playback View</span>
            </div>
          </div>
        </div>

        {/* Agent Decision Panel */}
        <div className="playback-panel agent-panel">
          <div className="panel-header">
            <span className="panel-title">
              <Brain size={16} /> Agent Decision
            </span>
          </div>
          <div className="panel-content">
            {iterationData?.decision ? (
              <div className="agent-decision">
                <div className="decision-action-row">
                  <span className="decision-action">{iterationData.decision.action}</span>
                  <span className="decision-confidence">
                    {((iterationData.decision.confidence || 0) * 100).toFixed(0)}% confidence
                  </span>
                </div>
                {iterationData.decision.reasoning && (
                  <div className="decision-reasoning">
                    <h4>Reasoning</h4>
                    <p>{iterationData.decision.reasoning}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="no-data">No decision data</div>
            )}
          </div>
        </div>
      </div>

      {/* Playback Controls Row */}
      <div className="playback-row playback-row-controls">
        <div className="playback-controls-bar">
          <button 
            className="btn btn-ghost"
            onClick={() => setSelectedSession(null)}
            title="Back to sessions"
          >
            <X size={18} /> Exit
          </button>

          <div className="controls-center">
            <button className="btn btn-icon" onClick={() => setCurrentIteration(1)} title="First">
              <SkipBack size={18} />
            </button>
            <button className="btn btn-icon" onClick={handlePrev} title="Previous">
              <ChevronLeft size={20} />
            </button>
            <button
              className={`btn btn-primary play-btn ${isPlaying ? 'playing' : ''}`}
              onClick={handlePlayPause}
            >
              {isPlaying ? <Pause size={24} /> : <Play size={24} />}
            </button>
            <button className="btn btn-icon" onClick={handleNext} title="Next">
              <ChevronRight size={20} />
            </button>
            <button
              className="btn btn-icon"
              onClick={() => setCurrentIteration(selectedSession.total_iterations)}
              title="Last"
            >
              <SkipForward size={18} />
            </button>
          </div>

          <div className="speed-control">
            <span>Speed:</span>
            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
            >
              <option value={0.5}>0.5x</option>
              <option value={1}>1x</option>
              <option value={2}>2x</option>
              <option value={4}>4x</option>
            </select>
          </div>
        </div>

        {/* Progress Slider */}
        <div className="progress-bar-container">
          <span className="progress-label">{currentIteration}</span>
          <input
            type="range"
            min={1}
            max={selectedSession.total_iterations}
            value={currentIteration}
            onChange={handleSliderChange}
            className="progress-slider"
          />
          <span className="progress-label">{selectedSession.total_iterations}</span>
        </div>
      </div>

      {/* Bottom row: Weather + Candidates + Metrics */}
      <div className="playback-row playback-row-bottom">
        {/* Weather Panel */}
        <div className="playback-panel weather-panel">
          <div className="panel-header">
            <span className="panel-title"><Cloud size={16} /> Weather</span>
          </div>
          <div className="panel-content">
            {iterationData?.weather ? (
              <div className="weather-grid">
                <div className="weather-item">
                  <span className="weather-label">Seeing</span>
                  <span className="weather-value">{iterationData.weather.seeing?.toFixed(2)}"</span>
                </div>
                <div className="weather-item">
                  <span className="weather-label">Clouds</span>
                  <span className="weather-value">
                    {((iterationData.weather.cloud_extinction || 0) * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="weather-item">
                  <span className="weather-label">Status</span>
                  <span className={`weather-status ${iterationData.weather.observability?.toLowerCase()}`}>
                    {iterationData.weather.observability || 'GOOD'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="no-data">No weather data</div>
            )}
          </div>
        </div>

        {/* Candidates Panel */}
        <div className="playback-panel candidates-panel">
          <div className="panel-header">
            <span className="panel-title">
              <Target size={16} /> Candidates ({iterationData?.candidates?.length || 0})
            </span>
          </div>
          <div className="panel-content candidates-list">
            {iterationData?.candidates?.length > 0 ? (
              iterationData.candidates.map((c, idx) => (
                <div key={c.id || idx} className="candidate-item">
                  <span 
                    className="candidate-status-dot"
                    style={{ backgroundColor: getStatusColor(c.status) }}
                  />
                  <span className="candidate-id">{c.id?.slice(0, 8) || `C${idx + 1}`}</span>
                  <span className="candidate-status" style={{ color: getStatusColor(c.status) }}>
                    {c.status}
                  </span>
                  <span className="candidate-confidence">
                    {((c.confidence || 0) * 100).toFixed(0)}%
                  </span>
                </div>
              ))
            ) : (
              <div className="no-data">No candidates</div>
            )}
          </div>
        </div>

        {/* Session Info Panel */}
        <div className="playback-panel info-panel">
          <div className="panel-header">
            <span className="panel-title"><History size={16} /> Session Info</span>
          </div>
          <div className="panel-content">
            <div className="info-grid">
              <span className="info-label">Started</span>
              <span className="info-value">{formatDate(selectedSession.start_time)}</span>
              <span className="info-label">Iterations</span>
              <span className="info-value">{selectedSession.total_iterations}</span>
              <span className="info-label">Confirmed</span>
              <span className="info-value confirmed">{selectedSession.confirmed_count || 0}</span>
              <span className="info-label">Rejected</span>
              <span className="info-value rejected">{selectedSession.rejected_count || 0}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Playback
