import { useState, useEffect } from 'react'
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
} from 'lucide-react'
import './Playback.css'

function Playback() {
  const [executions, setExecutions] = useState([])
  const [selectedExecution, setSelectedExecution] = useState(null)
  const [currentIteration, setCurrentIteration] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)

  // Fetch stored executions
  useEffect(() => {
    const fetchExecutions = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/executions')
        if (response.ok) {
          const data = await response.json()
          setExecutions(data.executions || [])
        }
      } catch (error) {
        console.error('Failed to fetch executions:', error)
      }
    }

    fetchExecutions()
  }, [])

  // Auto-advance playback
  useEffect(() => {
    if (!isPlaying || !selectedExecution) return

    const interval = setInterval(() => {
      setCurrentIteration(prev => {
        if (prev >= selectedExecution.total_iterations - 1) {
          setIsPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, 2000 / playbackSpeed)

    return () => clearInterval(interval)
  }, [isPlaying, selectedExecution, playbackSpeed])

  const handleSelectExecution = (execution) => {
    setSelectedExecution(execution)
    setCurrentIteration(0)
    setIsPlaying(false)
  }

  const handlePlayPause = () => setIsPlaying(!isPlaying)
  const handlePrev = () => setCurrentIteration(prev => Math.max(0, prev - 1))
  const handleNext = () => {
    if (selectedExecution) {
      setCurrentIteration(prev => Math.min(selectedExecution.total_iterations - 1, prev + 1))
    }
  }
  const handleReset = () => setCurrentIteration(0)

  return (
    <div className="playback-page">
      <div className="playback-header">
        <h1>
          <History size={24} />
          Marathon Playback
        </h1>
        <p>Replay past observation sessions and analyze agent decisions</p>
      </div>

      <div className="playback-content">
        {/* Execution list */}
        <div className="execution-list card">
          <div className="card-header">
            <span className="card-title">Saved Sessions</span>
          </div>
          <div className="execution-items">
            {executions.length === 0 ? (
              <div className="empty-state">
                <History size={32} />
                <p>No saved sessions yet</p>
                <span>Run a marathon to create recordings</span>
              </div>
            ) : (
              executions.map(exec => (
                <div
                  key={exec.id}
                  className={`execution-item ${selectedExecution?.id === exec.id ? 'selected' : ''}`}
                  onClick={() => handleSelectExecution(exec)}
                >
                  <div className="execution-info">
                    <div className="execution-date">
                      <Calendar size={14} />
                      {new Date(exec.timestamp).toLocaleDateString()}
                    </div>
                    <div className="execution-stats">
                      <span><Clock size={12} /> {exec.total_iterations} iterations</span>
                      <span><Target size={12} /> {exec.confirmed_count} confirmed</span>
                    </div>
                  </div>
                  <ChevronRight size={16} className="chevron" />
                </div>
              ))
            )}
          </div>
        </div>

        {/* Playback viewer */}
        <div className="playback-viewer card">
          {!selectedExecution ? (
            <div className="empty-state">
              <Play size={48} />
              <p>Select a session to begin playback</p>
            </div>
          ) : (
            <>
              <div className="viewer-header">
                <h3>Session: {new Date(selectedExecution.timestamp).toLocaleString()}</h3>
                <span className="iteration-display">
                  Iteration {currentIteration + 1} / {selectedExecution.total_iterations}
                </span>
              </div>

              <div className="viewer-content">
                {/* Placeholder for iteration data */}
                <div className="iteration-preview">
                  <p>Iteration {currentIteration + 1} data would display here</p>
                  <p className="hint">Showing agent decisions, images, and candidates</p>
                </div>
              </div>

              <div className="playback-controls">
                <button className="btn btn-icon" onClick={handleReset} title="Reset">
                  <SkipBack size={18} />
                </button>
                <button className="btn btn-icon" onClick={handlePrev} title="Previous">
                  <ChevronLeft size={18} />
                </button>
                <button
                  className={`btn btn-primary play-btn ${isPlaying ? 'playing' : ''}`}
                  onClick={handlePlayPause}
                >
                  {isPlaying ? <Pause size={20} /> : <Play size={20} />}
                </button>
                <button className="btn btn-icon" onClick={handleNext} title="Next">
                  <ChevronRight size={18} />
                </button>
                <button
                  className="btn btn-icon"
                  onClick={() => setCurrentIteration(selectedExecution.total_iterations - 1)}
                  title="End"
                >
                  <SkipForward size={18} />
                </button>

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

              {/* Progress bar */}
              <div className="playback-progress">
                <input
                  type="range"
                  min={0}
                  max={selectedExecution.total_iterations - 1}
                  value={currentIteration}
                  onChange={(e) => setCurrentIteration(Number(e.target.value))}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default Playback
