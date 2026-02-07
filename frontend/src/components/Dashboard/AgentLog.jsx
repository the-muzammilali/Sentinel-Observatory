import { useState, useEffect, useRef, useCallback } from 'react'
import { Brain, ChevronDown, ChevronRight, Zap, Clock } from 'lucide-react'
import './AgentLog.css'

function AgentLog({ marathonState }) {
  const [logs, setLogs] = useState([])
  const [expandedLogs, setExpandedLogs] = useState({})
  const [autoScroll, setAutoScroll] = useState(true)
  const logContainerRef = useRef(null)
  const logIdRef = useRef(0)
  const historyFetchedRef = useRef(false)

  // Generate unique ID for each log
  const getNextLogId = useCallback(() => {
    logIdRef.current += 1
    return `log_${Date.now()}_${logIdRef.current}`
  }, [])

  // Handle incoming log messages
  const handleLogMessage = useCallback((data) => {
    // Use sim_time from backend, or iteration-based fallback
    const simTime = data.sim_time || `Iter ${data.iteration || '?'}`
    
    switch (data.type) {
      case 'thinking':
        // Streaming token - update current thinking log
        setLogs(prev => {
          const last = prev[prev.length - 1]
          if (last?.type === 'thinking' && last.iteration === data.iteration) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + data.content }
            ]
          }
          return [...prev, {
            id: getNextLogId(),
            type: 'thinking',
            iteration: data.iteration,
            content: data.content,
            simTime: simTime,
          }]
        })
        break
      
      case 'deliberation':
        setLogs(prev => [...prev, {
          id: getNextLogId(),
          type: 'deliberation',
          iteration: data.iteration,
          content: data.content,
          simTime: simTime,
          // Action/confidence will be updated by subsequent decision event
          action: null,
          confidence: null,
        }])
        break
      
      case 'decision':
        // Update the most recent deliberation with action/confidence info
        setLogs(prev => {
          const lastDelibIdx = [...prev].reverse().findIndex(
            log => log.type === 'deliberation' && log.iteration === data.iteration
          )
          
          if (lastDelibIdx >= 0) {
            const idx = prev.length - 1 - lastDelibIdx
            const updated = [...prev]
            updated[idx] = {
              ...updated[idx],
              action: data.action,
              confidence: data.confidence,
            }
            return updated
          }
          
          // Fallback: create standalone decision entry if no matching deliberation
          return [...prev, {
            id: getNextLogId(),
            type: 'decision',
            iteration: data.iteration,
            action: data.action,
            reasoning: data.reasoning,
            confidence: data.confidence,
            simTime: simTime,
          }]
        })
        break
      
      default:
        setLogs(prev => [...prev, {
          id: getNextLogId(),
          type: 'info',
          content: data.content || JSON.stringify(data),
          simTime: simTime,
        }])
    }
  }, [getNextLogId])

  // SSE connection for real-time log streaming
  useEffect(() => {
    if (!marathonState.isRunning) return

    let eventSource = null
    
    try {
      eventSource = new EventSource('http://localhost:8000/stream/agent-log')

      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data)
        handleLogMessage(data)
      }

      eventSource.onerror = () => {
        // Suppress logging - reconnection is handled by browser
        eventSource?.close()
      }
    } catch {
      // Failed to connect - will retry on next render
    }

    return () => {
      eventSource?.close()
    }
  }, [marathonState.isRunning, handleLogMessage])

  // Fetch log history on mount if marathon is running (for page refresh recovery)
  useEffect(() => {
    const fetchLogHistory = async () => {
      // Only fetch once per component lifecycle
      if (!marathonState.isRunning || historyFetchedRef.current) return
      historyFetchedRef.current = true
      
      try {
        const response = await fetch('http://localhost:8000/api/marathon/logs')
        if (response.ok) {
          const data = await response.json()
          if (data.logs && data.logs.length > 0) {
            // Process each historical log through handleLogMessage
            data.logs.forEach(log => handleLogMessage(log))
          }
        }
      } catch (error) {
        console.warn('Failed to fetch log history:', error)
      }
    }
    
    fetchLogHistory()
  // Only run when marathon state changes - ref prevents duplicate fetches
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marathonState.isRunning])

  // Note: Component remounts via key={resetKey} in parent, so state automatically resets

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const toggleExpand = (logId) => {
    setExpandedLogs(prev => ({
      ...prev,
      [logId]: !prev[logId]
    }))
  }

  const getActionBadgeClass = (action) => {
    if (action?.includes('observe')) return 'observe'
    if (action?.includes('slew')) return 'slew'
    if (action?.includes('alert') || action?.includes('trigger')) return 'alert'
    if (action?.includes('wait')) return 'wait'
    return 'default'
  }

  const getConfidenceClass = (confidence) => {
    if (confidence >= 0.8) return 'high'
    if (confidence >= 0.5) return 'medium'
    return 'low'
  }

  const formatAction = (action) => {
    return action?.replace(/_/g, ' ') || 'unknown'
  }

  return (
    <div className="agent-log">
      <div className="panel-header">
        <div className="panel-title">
          <Brain size={16} />
          <span>Agent Reasoning</span>
        </div>
        <div className="auto-scroll-toggle">
          <span>Auto-scroll</span>
          <label className="switch">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            <span className="slider round"></span>
          </label>
        </div>
      </div>

      <div className="log-container" ref={logContainerRef}>
        {logs.length === 0 ? (
          <div className="log-placeholder">
            <p>Waiting for agent activity...</p>
          </div>
        ) : (
          logs.map(log => (
            <div key={log.id} className={`log-entry log-${log.type} animate-slide-up`}>
              {log.type === 'decision' ? (
                <>
                  <div
                    className="log-header clickable"
                    onClick={() => toggleExpand(log.id)}
                  >
                    {expandedLogs[log.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span className={`action-badge ${getActionBadgeClass(log.action)}`}>
                      <Zap size={10} />
                      {formatAction(log.action)}
                    </span>
                    <div className="confidence-indicator">
                      <div className="confidence-bar">
                        <div 
                          className={`confidence-fill ${getConfidenceClass(log.confidence)}`}
                          style={{ width: `${(log.confidence * 100)}%` }}
                        />
                      </div>
                      <span className="confidence-text">{(log.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <span className="sim-time">
                      <Clock size={10} /> {log.simTime}
                    </span>
                    <span className="log-iteration">#{log.iteration}</span>
                  </div>
                  {expandedLogs[log.id] && (
                    <div className="log-content expanded">
                      <p>{log.reasoning}</p>
                    </div>
                  )}
                </>
              ) : log.type === 'deliberation' ? (
                <>
                  <div
                    className="log-header clickable"
                    onClick={() => toggleExpand(log.id)}
                  >
                    {expandedLogs[log.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <Brain size={14} />
                    <span className="log-label">Deliberation</span>
                    {log.action && (
                      <span className={`action-badge ${getActionBadgeClass(log.action)}`}>
                        <Zap size={10} />
                        {formatAction(log.action)}
                      </span>
                    )}
                    {log.confidence != null && (
                      <div className="confidence-indicator">
                        <div className="confidence-bar">
                          <div 
                            className={`confidence-fill ${getConfidenceClass(log.confidence)}`}
                            style={{ width: `${(log.confidence * 100)}%` }}
                          />
                        </div>
                        <span className="confidence-text">{(log.confidence * 100).toFixed(0)}%</span>
                      </div>
                    )}
                    <span className="sim-time">
                      <Clock size={10} /> {log.simTime}
                    </span>
                    <span className="log-iteration">#{log.iteration}</span>
                  </div>
                  {expandedLogs[log.id] && (
                    <div className="log-content expanded deliberation-content">
                      <pre>{log.content}</pre>
                    </div>
                  )}
                </>
              ) : log.type === 'thinking' ? (
                <div className="log-thinking">
                  <Brain size={14} className="thinking-icon" />
                  <span className="thinking-text">{log.content}</span>
                  <span className="thinking-cursor">▊</span>
                </div>
              ) : (
                <div className="log-info">
                  <span>{log.content}</span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default AgentLog
