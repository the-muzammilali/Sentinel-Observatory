import { useState } from 'react'
import { Settings as SettingsIcon, Save, RotateCcw, Zap, Globe, Cpu, Server } from 'lucide-react'
import './Settings.css'

const DEFAULT_CONFIG = {
  max_iterations: 16,
  num_stars: 100,
  num_transients: 2,
  inject_false_positives: true,
  false_positive_rate: 0.3,
  step_interval_hours: 0.5,
  confirm_threshold: 0.8,
  weather_enabled: true,
  auto_save_executions: true,
  api_url: 'http://localhost:8000',
}

// Load saved config from localStorage
function loadSavedConfig() {
  try {
    const saved = localStorage.getItem('sentinel-config')
    if (saved) {
      return { ...DEFAULT_CONFIG, ...JSON.parse(saved) }
    }
  } catch {
    // Invalid JSON, use defaults
  }
  return DEFAULT_CONFIG
}

function Settings() {
  const [config, setConfig] = useState(loadSavedConfig)
  const [saved, setSaved] = useState(false)

  const handleChange = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = () => {
    // Save to localStorage
    localStorage.setItem('sentinel-config', JSON.stringify(config))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleReset = () => {
    setConfig(DEFAULT_CONFIG)
    localStorage.removeItem('sentinel-config')
    setSaved(false)
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>
          <SettingsIcon size={28} />
          Settings
        </h1>
        <p>Configure marathon parameters and application preferences</p>
      </div>

      <div className="settings-grid">
        {/* Left Column - Simulation Environment */}
        <div className="settings-column">
          <div className="settings-card">
            <div className="card-header">
              <Globe className="card-icon" size={20} />
              <h3>Simulation Environment</h3>
            </div>
            
            <div className="settings-group-grid">
              <div className="setting-item">
                <label>Maximum Iterations</label>
                <input
                  type="number"
                  value={config.max_iterations}
                  onChange={(e) => handleChange('max_iterations', parseInt(e.target.value))}
                  min={1}
                  max={100}
                />
                <span className="setting-description">OODA cycles per marathon</span>
              </div>

              <div className="setting-item">
                <label>Step Interval (hours)</label>
                <input
                  type="number"
                  value={config.step_interval_hours}
                  onChange={(e) => handleChange('step_interval_hours', parseFloat(e.target.value))}
                  min={0.1}
                  max={24}
                  step={0.1}
                />
                <span className="setting-description">Time between iterations</span>
              </div>

              <div className="setting-item">
                <label>Number of Stars</label>
                <input
                  type="number"
                  value={config.num_stars}
                  onChange={(e) => handleChange('num_stars', parseInt(e.target.value))}
                  min={10}
                  max={500}
                />
                <span className="setting-description">Background star field density</span>
              </div>

              <div className="setting-item">
                <label>Number of Transients</label>
                <input
                  type="number"
                  value={config.num_transients}
                  onChange={(e) => handleChange('num_transients', parseInt(e.target.value))}
                  min={0}
                  max={10}
                />
                <span className="setting-description">Actual transient events to inject</span>
              </div>
            </div>

            <div className="setting-divider"></div>

            <div className="setting-toggle">
              <div className="toggle-info">
                <label>Weather Simulation</label>
                <span className="setting-description">Simulate variable seeing and cloud conditions</span>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={config.weather_enabled}
                  onChange={(e) => handleChange('weather_enabled', e.target.checked)}
                />
                <span className="slider round"></span>
              </label>
            </div>
          </div>
        </div>

        {/* Right Column - Agent Logic & System */}
        <div className="settings-column">
          <div className="settings-card">
            <div className="card-header">
              <Cpu className="card-icon" size={20} />
              <h3>Agent Logic</h3>
            </div>

            <div className="setting-slider-group">
              <div className="slider-header">
                <label>Confirmation Threshold</label>
                <span className="slider-value">{(config.confirm_threshold * 100).toFixed(0)}%</span>
              </div>
              <input
                type="range"
                value={config.confirm_threshold}
                onChange={(e) => handleChange('confirm_threshold', parseFloat(e.target.value))}
                min={0.5}
                max={1}
                step={0.05}
              />
              <span className="setting-description">Confidence required to confirm a candidate</span>
            </div>

            <div className="setting-divider"></div>

            <div className="setting-toggle">
              <div className="toggle-info">
                <label>Inject False Positives</label>
                <span className="setting-description">Add decoy detections to test discrimination</span>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={config.inject_false_positives}
                  onChange={(e) => handleChange('inject_false_positives', e.target.checked)}
                />
                <span className="slider round"></span>
              </label>
            </div>

            {config.inject_false_positives && (
              <div className="setting-slider-group nested">
                <div className="slider-header">
                  <label>False Positive Rate</label>
                  <span className="slider-value">{(config.false_positive_rate * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  value={config.false_positive_rate}
                  onChange={(e) => handleChange('false_positive_rate', parseFloat(e.target.value))}
                  min={0}
                  max={1}
                  step={0.1}
                />
              </div>
            )}
          </div>

          <div className="settings-card">
            <div className="card-header">
              <Server className="card-icon" size={20} />
              <h3>System Preferences</h3>
            </div>

            <div className="setting-item full-width">
              <label>API URL</label>
              <input
                type="text"
                value={config.api_url}
                onChange={(e) => handleChange('api_url', e.target.value)}
                placeholder="http://localhost:8000"
              />
            </div>

            <div className="setting-toggle">
              <div className="toggle-info">
                <label>Auto-save Executions</label>
                <span className="setting-description">Automatically save marathons for playback</span>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={config.auto_save_executions}
                  onChange={(e) => handleChange('auto_save_executions', e.target.checked)}
                />
                <span className="slider round"></span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div className="settings-footer">
        <button className="btn btn-secondary" onClick={handleReset}>
          <RotateCcw size={16} />
          Reset Defaults
        </button>
        <button className={`btn btn-primary ${saved ? 'saved' : ''}`} onClick={handleSave}>
          <Save size={16} />
          {saved ? 'Saved Successfully' : 'Save Changes'}
        </button>
      </div>
    </div>
  )
}

export default Settings
