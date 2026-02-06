import { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Header from './components/Layout/Header'
import Sidebar from './components/Layout/Sidebar'
import Dashboard from './pages/Dashboard'
import Playback from './pages/Playback'
import Settings from './pages/Settings'
import './App.css'

function App() {
  const [marathonState, setMarathonState] = useState({
    isRunning: false,
    isPaused: false,
    currentIteration: 0,
    maxIterations: 16,
    status: 'idle', // 'idle' | 'running' | 'paused' | 'completed' | 'error'
    startTime: null,
  })

  const [contextState, setContextState] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)

  // Message handler for WebSocket
  const handleWsMessage = useCallback((data) => {
    switch (data.type) {
      case 'state_update':
        setMarathonState(prev => ({
          ...prev,
          ...data.marathon,
        }))
        if (data.context) {
          setContextState(data.context)
        }
        break
      case 'iteration_complete':
        setMarathonState(prev => ({
          ...prev,
          currentIteration: data.iteration,
        }))
        if (data.context) {
          setContextState(data.context)
        }
        break
      case 'marathon_complete':
        setMarathonState(prev => ({
          ...prev,
          isRunning: false,
          status: 'completed',
        }))
        break
      case 'error':
        setMarathonState(prev => ({
          ...prev,
          status: 'error',
          error: data.message,
        }))
        break
      default:
        // Ignore unknown message types (heartbeat, pong, etc.)
        break
    }
  }, [])

  // WebSocket connection for real-time updates
  useEffect(() => {
    let ws = null
    let reconnectTimeout = null
    let isCleanup = false
    let reconnectAttempts = 0
    const maxReconnectAttempts = 10

    const connect = () => {
      if (isCleanup) return

      try {
        ws = new WebSocket('ws://localhost:8000/ws/marathon')

        ws.onopen = () => {
          if (!isCleanup) {
            console.log('✅ WebSocket connected')
            setWsConnected(true)
            reconnectAttempts = 0
          }
        }

        ws.onmessage = (event) => {
          if (!isCleanup) {
            try {
              const data = JSON.parse(event.data)
              // Ignore heartbeat messages
              if (data.type !== 'heartbeat') {
                handleWsMessage(data)
              }
            } catch {
              // Ignore parse errors for keepalive messages
            }
          }
        }

        ws.onclose = (event) => {
          if (!isCleanup) {
            setWsConnected(false)
            // Only log and reconnect if not a clean close
            if (!event.wasClean && reconnectAttempts < maxReconnectAttempts) {
              reconnectAttempts++
              const delay = Math.min(3000 * reconnectAttempts, 10000)
              console.log(`🔄 WebSocket reconnecting in ${delay/1000}s (attempt ${reconnectAttempts})...`)
              reconnectTimeout = setTimeout(connect, delay)
            } else if (reconnectAttempts >= maxReconnectAttempts) {
              console.log('❌ WebSocket max reconnection attempts reached')
            }
          }
        }

        ws.onerror = () => {
          // Suppress error logging - onclose will handle it
        }
      } catch {
        if (!isCleanup && reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++
          reconnectTimeout = setTimeout(connect, 3000)
        }
      }
    }

    connect()

    return () => {
      isCleanup = true
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, 'Component unmounting')
      }
    }
  }, [handleWsMessage])

  const handleStartMarathon = async (config) => {
    try {
      const response = await fetch('http://localhost:8000/api/marathon/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await response.json()
      if (data.success) {
        setMarathonState(prev => ({
          ...prev,
          isRunning: true,
          status: 'running',
          currentIteration: 0,
          maxIterations: config.max_iterations || 16,
          startTime: new Date().toISOString(),
        }))
      }
    } catch (error) {
      console.error('Failed to start marathon:', error)
    }
  }

  const handleStopMarathon = async () => {
    try {
      await fetch('http://localhost:8000/api/marathon/stop', { method: 'POST' })
      setMarathonState(prev => ({
        ...prev,
        isRunning: false,
        status: 'idle',
      }))
    } catch (error) {
      console.error('Failed to stop marathon:', error)
    }
  }

  const handlePauseMarathon = async () => {
    try {
      await fetch('http://localhost:8000/api/marathon/pause', { method: 'POST' })
      setMarathonState(prev => ({
        ...prev,
        isPaused: !prev.isPaused,
        status: prev.isPaused ? 'running' : 'paused',
      }))
    } catch (error) {
      console.error('Failed to pause marathon:', error)
    }
  }

  return (
    <BrowserRouter>
      <div className="app">
        <Header
          marathonState={marathonState}
          wsConnected={wsConnected}
        />
        <div className="app-content">
          <Sidebar
            marathonState={marathonState}
            contextState={contextState}
            onStart={handleStartMarathon}
            onStop={handleStopMarathon}
            onPause={handlePauseMarathon}
          />
          <main className="main-content">
            <Routes>
              <Route
                path="/"
                element={
                  <Dashboard
                    marathonState={marathonState}
                    contextState={contextState}
                  />
                }
              />
              <Route path="/playback" element={<Playback />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}

export default App
