import { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Header from './components/Layout/Header'
import Sidebar from './components/Layout/Sidebar'
import Login from './components/Login/Login'
import Dashboard from './pages/Dashboard'
import Playback from './pages/Playback'
import Settings from './pages/Settings'
import './App.css'

// Hardcode to empty string to ensure relative path usage with Nginx proxy
const API_BASE_URL = '' // import.meta.env.VITE_API_URL || ''

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authToken, setAuthToken] = useState(null)
  const [username, setUsername] = useState(null)
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)

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
  // Key that increments on each new marathon to force child components to remount fresh
  const [marathonResetKey, setMarathonResetKey] = useState(0)

  // Check for existing auth token on mount
  useEffect(() => {
    const token = localStorage.getItem('auth_token')
    const storedUsername = localStorage.getItem('username')
    
    if (token) {
      // Verify token is still valid
      fetch(`${API_BASE_URL}/api/auth/verify`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
        .then(res => res.json())
        .then(data => {
          if (data.authenticated) {
            setAuthToken(token)
            setUsername(storedUsername || data.username)
            setIsAuthenticated(true)
          } else {
            // Token invalid, clear it
            localStorage.removeItem('auth_token')
            localStorage.removeItem('username')
          }
        })
        .catch(() => {
          // Token verification failed, clear it
          localStorage.removeItem('auth_token')
          localStorage.removeItem('username')
        })
        .finally(() => {
          setIsCheckingAuth(false)
        })
    } else {
      setIsCheckingAuth(false)
    }
  }, [])

  const handleLoginSuccess = (token, user) => {
    setAuthToken(token)
    setUsername(user)
    setIsAuthenticated(true)
  }

  const handleLogout = () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('username')
    setAuthToken(null)
    setUsername(null)
    setIsAuthenticated(false)
  }

  // Message handler for WebSocket
  const handleWsMessage = useCallback((data) => {
    switch (data.type) {
      case 'state_update':
        setMarathonState(prev => ({
          ...prev,
          ...data.marathon,
        }))
        // Always update contextState (including null to clear old data)
        setContextState(data.context ?? null)
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
    if (!isAuthenticated) return

    let ws = null
    let reconnectTimeout = null
    let isCleanup = false
    let reconnectAttempts = 0
    const maxReconnectAttempts = 10

    const connect = () => {
      if (isCleanup) return

      try {
        // Determine WebSocket protocol and host
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        // Use current host for WebSocket connection (handled by Nginx proxy)
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/marathon?token=${authToken}`
        
        ws = new WebSocket(wsUrl)

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
  }, [handleWsMessage, isAuthenticated, authToken])

  const handleStartMarathon = async (config) => {
    // Clear all state for a fresh marathon start
    setContextState(null)
    setMarathonResetKey(prev => prev + 1) // Force child components to remount
    setMarathonState(prev => ({
      ...prev,
      currentIteration: 0,
      status: 'idle',
      error: undefined,
    }))

    try {
      const response = await fetch(`${API_BASE_URL}/api/marathon/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
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
      await fetch(`${API_BASE_URL}/api/marathon/stop`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      })
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
      await fetch(`${API_BASE_URL}/api/marathon/pause`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      })
      setMarathonState(prev => ({
        ...prev,
        isPaused: !prev.isPaused,
        status: prev.isPaused ? 'running' : 'paused',
      }))
    } catch (error) {
      console.error('Failed to pause marathon:', error)
    }
  }

  // Show loading while checking auth
  if (isCheckingAuth) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%)',
        color: '#fff'
      }}>
        <div>Loading...</div>
      </div>
    )
  }

  // Show login if not authenticated
  if (!isAuthenticated) {
    return <Login onLoginSuccess={handleLoginSuccess} />
  }

  return (
    <BrowserRouter>
      <div className="app">
        <Header
          marathonState={marathonState}
          wsConnected={wsConnected}
          username={username}
          onLogout={handleLogout}
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
                    resetKey={marathonResetKey}
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
