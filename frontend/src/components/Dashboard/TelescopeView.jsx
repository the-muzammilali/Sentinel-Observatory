import { useState, useEffect, useCallback, useRef } from 'react'
import { Camera, ZoomIn, ZoomOut, Layers, RefreshCw, Move } from 'lucide-react'
import './TelescopeView.css'

function TelescopeView({ marathonState, currentIteration }) {
  const [imageUrl, setImageUrl] = useState(null)
  const [showDiff, setShowDiff] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  // Pan mode toggle and state
  const [panMode, setPanMode] = useState(false)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 })
  
  // Track what we've already loaded to prevent reloading
  const loadedRef = useRef({ iteration: null, showDiff: false })
  const imageUrlRef = useRef(null)

  const loadImage = useCallback(async () => {
    if (!currentIteration) return
    
    // Skip if already loaded this exact combination
    if (loadedRef.current.iteration === currentIteration && 
        loadedRef.current.showDiff === showDiff) {
      return
    }
    
    setLoading(true)
    setError(null)
    try {
      const type = showDiff ? 'diff' : 'current'
      const url = `http://localhost:8000/api/iteration/${currentIteration}/image?type=${type}`
      const response = await fetch(url)
      
      if (response.ok) {
        const blob = await response.blob()
        // Revoke old URL to prevent memory leak
        if (imageUrlRef.current) {
          URL.revokeObjectURL(imageUrlRef.current)
        }
        const newUrl = URL.createObjectURL(blob)
        imageUrlRef.current = newUrl
        setImageUrl(newUrl)
        loadedRef.current = { iteration: currentIteration, showDiff }
      } else {
        console.warn(`Image not available: ${response.status}`)
        setError(`Image not available (iteration ${currentIteration})`)
      }
    } catch (err) {
      console.error('Failed to load image:', err)
      setError('Failed to connect to server')
    } finally {
      setLoading(false)
    }
  }, [currentIteration, showDiff])

  useEffect(() => {
    if (currentIteration && marathonState.isRunning) {
      loadImage()
    }
  }, [currentIteration, showDiff, marathonState.isRunning, loadImage])

  // Reset pan when zoom resets to 1
  useEffect(() => {
    if (zoom === 1) {
      setPan({ x: 0, y: 0 })
    }
  }, [zoom])

  // Mouse event handlers for pan mode
  const handleMouseDown = (e) => {
    if (!panMode) return
    
    e.preventDefault()
    setIsDragging(true)
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: pan.x,
      panY: pan.y
    }
  }

  const handleMouseMove = useCallback((e) => {
    if (!isDragging) return
    
    const dx = e.clientX - dragStartRef.current.x
    const dy = e.clientY - dragStartRef.current.y
    
    // Calculate max pan based on zoom level (allow some pan at 100% too)
    const maxPan = Math.max(100, (zoom - 1) * 200 + 100)
    
    setPan({
      x: Math.max(-maxPan, Math.min(maxPan, dragStartRef.current.panX + dx)),
      y: Math.max(-maxPan, Math.min(maxPan, dragStartRef.current.panY + dy))
    })
  }, [isDragging, zoom])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  // Global mouse event listeners
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

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.5, 4))
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.5, 0.5))
  const handleReset = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
    setPanMode(false)
  }
  
  const togglePanMode = () => {
    setPanMode(!panMode)
  }

  return (
    <div className="telescope-view">
      <div className="panel-header">
        <div className="panel-title">
          <Camera size={16} />
          <span>Telescope View</span>
        </div>
        <div className="panel-actions">
          <button
            className={`btn btn-icon ${showDiff ? 'active' : ''}`}
            onClick={() => setShowDiff(!showDiff)}
            title="Toggle difference image"
          >
            <Layers size={16} />
          </button>
          <div className="zoom-controls">
            <button className="btn btn-icon" onClick={handleZoomOut} title="Zoom out">
              <ZoomOut size={16} />
            </button>
            <span className="zoom-level">{(zoom * 100).toFixed(0)}%</span>
            <button className="btn btn-icon" onClick={handleZoomIn} title="Zoom in">
              <ZoomIn size={16} />
            </button>
          </div>
          <button 
            className={`btn btn-icon ${panMode ? 'active' : ''}`}
            onClick={togglePanMode}
            title={panMode ? 'Exit pan mode' : 'Enter pan mode'}
          >
            <Move size={16} />
          </button>
          <button className="btn btn-icon" onClick={handleReset} title="Reset view">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      <div 
        className={`telescope-content ${panMode ? 'pan-mode' : ''} ${isDragging ? 'is-dragging' : ''}`}
        onMouseDown={handleMouseDown}
      >
        {/* Space background with stars */}
        <div className="space-background">
          <div className="stars stars-small"></div>
          <div className="stars stars-medium"></div>
        </div>
        
        {/* Vignette overlay */}
        <div className="vignette-overlay"></div>
        
        {loading && (
          <div className="loading-overlay">
            <div className="loading-spinner" />
            <span>Loading observation...</span>
          </div>
        )}

        {imageUrl ? (
          <div 
            className="image-container" 
            style={{ 
              transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
            }}
          >
            <img
              src={imageUrl}
              alt={showDiff ? 'Difference image' : 'Current observation'}
              className="telescope-image"
              draggable={false}
            />
            {showDiff && (
              <div className="image-badge">DIFF</div>
            )}
          </div>
        ) : (
          <div className="placeholder">
            <Camera size={48} />
            <p>{error || 'No observation loaded'}</p>
            <span className="placeholder-hint">
              {marathonState.isRunning 
                ? `Waiting for iteration ${currentIteration || 1} image...`
                : 'Start a marathon to capture images'}
            </span>
          </div>
        )}
        
        {/* Pan mode indicator */}
        {panMode && (
          <div className="pan-mode-indicator">
            <Move size={14} />
            <span>Pan Mode - Drag to move</span>
          </div>
        )}
      </div>

      <div className="telescope-footer">
        <span className="footer-info">
          {showDiff ? 'Difference Image (Reference - Current)' : 'Current Observation'}
        </span>
        {currentIteration && (
          <span className="footer-iteration">
            Iteration {currentIteration}
          </span>
        )}
      </div>
    </div>
  )
}

export default TelescopeView
