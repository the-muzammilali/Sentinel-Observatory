import { useState } from 'react'
import { Settings as SettingsIcon, Save, RotateCcw } from 'lucide-react'
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
          <SettingsIcon size={24} />
          Settings
        </h1>
        <p>Configure marathon parameters and application settings</p>
      </div>

      <div className="settings-content">
        <div className="settings-section card">
          <h3>Marathon Configuration</h3>

          <div className="setting-group">
            <label className="setting-label">
              <span>Maximum Iterations</span>
              <span className="setting-hint">Number of OODA cycles per marathon</span>
            </label>
            <input
              type="number"
              value={config.max_iterations}
              onChange={(e) => handleChange('max_iterations', parseInt(e.target.value))}
              min={1}
              max={100}
            />
          </div>

          <div className="setting-group">
            <label className="setting-label">
              <span>Number of Stars</span>
              <span className="setting-hint">Background stars in simulation</span>
            </label>
            <input
              type="number"
              value={config.num_stars}
              onChange={(e) => handleChange('num_stars', parseInt(e.target.value))}
              min={10}
              max={500}
            />
          </div>

          <div className="setting-group">
            <label className="setting-label">
              <span>Number of Transients</span>
              <span className="setting-hint">Actual transient events to inject</span>
            </label>
            <input
              type="number"
              value={config.num_transients}
              onChange={(e) => handleChange('num_transients', parseInt(e.target.value))}
              min={0}
              max={10}
            />
          </div>

          <div className="setting-group">
            <label className="setting-label">
              <span>Step Interval (hours)</span>
              <span className="setting-hint">Simulated time between iterations</span>
            </label>
            <input
              type="number"
              value={config.step_interval_hours}
              onChange={(e) => handleChange('step_interval_hours', parseFloat(e.target.value))}
              min={0.1}
              max={24}
              step={0.1}
            />
          </div>
        </div>

        <div className="settings-section card">
          <h3>Detection Settings</h3>

          <div className="setting-group checkbox">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.inject_false_positives}
                onChange={(e) => handleChange('inject_false_positives', e.target.checked)}
              />
              <span>Inject False Positives</span>
            </label>
            <span className="setting-hint">Add decoy detections to test agent discrimination</span>
          </div>

          {config.inject_false_positives && (
            <div className="setting-group">
              <label className="setting-label">
                <span>False Positive Rate</span>
                <span className="setting-hint">Probability of false positive per iteration</span>
              </label>
              <input
                type="range"
                value={config.false_positive_rate}
                onChange={(e) => handleChange('false_positive_rate', parseFloat(e.target.value))}
                min={0}
                max={1}
                step={0.1}
              />
              <span className="range-value">{(config.false_positive_rate * 100).toFixed(0)}%</span>
            </div>
          )}

          <div className="setting-group">
            <label className="setting-label">
              <span>Confirmation Threshold</span>
              <span className="setting-hint">Confidence required to confirm a candidate</span>
            </label>
            <input
              type="range"
              value={config.confirm_threshold}
              onChange={(e) => handleChange('confirm_threshold', parseFloat(e.target.value))}
              min={0.5}
              max={1}
              step={0.05}
            />
            <span className="range-value">{(config.confirm_threshold * 100).toFixed(0)}%</span>
          </div>

          <div className="setting-group checkbox">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.weather_enabled}
                onChange={(e) => handleChange('weather_enabled', e.target.checked)}
              />
              <span>Enable Weather Simulation</span>
            </label>
            <span className="setting-hint">Variable seeing and cloud conditions</span>
          </div>
        </div>

        <div className="settings-section card">
          <h3>Application Settings</h3>

          <div className="setting-group checkbox">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.auto_save_executions}
                onChange={(e) => handleChange('auto_save_executions', e.target.checked)}
              />
              <span>Auto-save Executions</span>
            </label>
            <span className="setting-hint">Automatically save marathons for playback</span>
          </div>

          <div className="setting-group">
            <label className="setting-label">
              <span>API URL</span>
              <span className="setting-hint">Backend server address</span>
            </label>
            <input
              type="text"
              value={config.api_url}
              onChange={(e) => handleChange('api_url', e.target.value)}
              placeholder="http://localhost:8000"
            />
          </div>
        </div>
      </div>

      <div className="settings-actions">
        <button className="btn btn-secondary" onClick={handleReset}>
          <RotateCcw size={16} />
          Reset to Defaults
        </button>
        <button className={`btn btn-primary ${saved ? 'saved' : ''}`} onClick={handleSave}>
          <Save size={16} />
          {saved ? 'Saved!' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}

export default Settings
