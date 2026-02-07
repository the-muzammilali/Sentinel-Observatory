import { useState, useEffect, useMemo } from 'react'
import TelescopeView from '../components/Dashboard/TelescopeView'
import AgentLog from '../components/Dashboard/AgentLog'
import CandidateList from '../components/Dashboard/CandidateList'
import Timeline from '../components/Visualization/Timeline'
import LightCurve from '../components/Visualization/LightCurve'
import GroundTruth from '../components/Dashboard/GroundTruth'
import './Dashboard.css'

function Dashboard({ marathonState, contextState, resetKey }) {
  const [selectedCandidate, setSelectedCandidate] = useState(null)
  const [fetchedIterations, setFetchedIterations] = useState([])

  // Fetch iterations history from API
  useEffect(() => {
    const fetchIterations = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/iterations')
        if (response.ok) {
          const data = await response.json()
          setFetchedIterations(data.iterations || [])
        }
      } catch {
        // Fetch failed - will retry
      }
    }

    if (marathonState.isRunning) {
      const interval = setInterval(fetchIterations, 5000)
      fetchIterations()
      return () => clearInterval(interval)
    }
  }, [marathonState.isRunning])

  // Note: Child components remount via key={resetKey} so they automatically reset
  // Dashboard's fetchedIterations will naturally clear when no running marathon serves data

  // Merge fetched iterations with current context iteration
  const iterations = useMemo(() => {
    const result = [...fetchedIterations]
    if (contextState?.iteration) {
      const exists = result.some(i => i.iteration === contextState.iteration)
      if (!exists) {
        result.push({
          iteration: contextState.iteration,
          simulated_time: contextState.simulated_time,
          weather: contextState.weather,
          num_candidates: contextState.candidates?.length || 0,
        })
      }
    }
    return result
  }, [fetchedIterations, contextState])

  const candidates = contextState?.candidates || []
  
  // Update selected candidate with the latest data from context
  const fullSelectedCandidate = selectedCandidate 
    ? candidates.find(c => c.id === selectedCandidate.id) || selectedCandidate
    : null

  // Get current iteration - try multiple sources
  const currentIter = marathonState.currentIteration || contextState?.iteration

  return (
    <div className="dashboard">
      {/* Top row: Telescope + Agent Log */}
      <div className="dashboard-row dashboard-row-main">
        <div className="dashboard-panel telescope-panel">
          <TelescopeView
            key={`telescope-${resetKey}`}
            marathonState={marathonState}
            contextState={contextState}
            currentIteration={currentIter}
          />
        </div>
        <div className="dashboard-panel agent-panel">
          <AgentLog
            key={`agent-${resetKey}`}
            marathonState={marathonState}
            contextState={contextState}
          />
        </div>
      </div>

      {/* Middle row: Timeline */}
      <div className="dashboard-row dashboard-row-timeline">
        <div className="dashboard-panel timeline-panel">
          <Timeline
            iterations={iterations}
            currentIteration={marathonState.currentIteration}
          />
        </div>
      </div>

      {/* Bottom row: Candidates + Light Curve + Ground Truth */}
      <div className="dashboard-row dashboard-row-bottom">
        <div className="dashboard-panel candidates-panel">
          <CandidateList
            candidates={candidates}
            selectedCandidate={selectedCandidate}
            onSelectCandidate={setSelectedCandidate}
          />
        </div>
        <div className="dashboard-panel lightcurve-panel">
          <LightCurve
            candidate={fullSelectedCandidate}
          />
        </div>
        <div className="dashboard-panel groundtruth-panel">
          <GroundTruth
            key={`groundtruth-${resetKey}`}
            marathonState={marathonState}
          />
        </div>
      </div>
    </div>
  )
}

export default Dashboard
