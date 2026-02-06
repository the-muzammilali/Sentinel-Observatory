import { useState, useEffect, useRef, useCallback } from 'react'
import { Brain, ChevronDown, ChevronRight, Zap } from 'lucide-react'
import './AgentLog.css'

function AgentLog({ marathonState }) {
  const [logs, setLogs] = useState([])
  const [expandedLogs, setExpandedLogs] = useState({})
  const [autoScroll, setAutoScroll] = useState(true)
  const logContainerRef = useRef(null)
  const logIdRef = useRef(0)

  // Generate unique ID for each log
  const getNextLogId = useCallback(() => {
    logIdRef.current += 1
    return `log_${Date.now()}_${logIdRef.current}`
  }, [])

  // Handle incoming log messages
  const handleLogMessage = useCallback((data) => {
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
            timestamp: new Date().toISOString(),
          }]
        })
        break
      
      case 'deliberation':
        setLogs(prev => [...prev, {
          id: getNextLogId(),
          type: 'deliberation',
          iteration: data.iteration,
          content: data.content,
          timestamp: new Date().toISOString(),
        }])
        break
      
      case 'decision':
        setLogs(prev => [...prev, {
          id: getNextLogId(),
          type: 'decision',
          iteration: data.iteration,
          action: data.action,
          reasoning: data.reasoning,
          confidence: data.confidence,
          timestamp: new Date().toISOString(),
        }])
        break
      
      default:
        setLogs(prev => [...prev, {
          id: getNextLogId(),
          type: 'info',
          content: data.content || JSON.stringify(data),
          timestamp: new Date().toISOString(),
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

  const getActionColor = (action) => {
    switch (action) {
      case 'observe_again': return 'var(--accent-info)'
      case 'slew_to': return 'var(--accent-secondary)'
      case 'trigger_alert': return 'var(--accent-success)'
      case 'wait': return 'var(--accent-warning)'
      default: return 'var(--text-muted)'
    }
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
                    <Zap size={14} style={{ color: getActionColor(log.action) }} />
                    <span className="log-action" style={{ color: getActionColor(log.action) }}>
                      {log.action?.toUpperCase()}
                    </span>
                    <span className="log-confidence">
                      {(log.confidence * 100).toFixed(0)}% confidence
                    </span>
                    <span className="log-iteration">Iter {log.iteration}</span>
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
                    <span className="log-iteration">Iter {log.iteration}</span>
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
