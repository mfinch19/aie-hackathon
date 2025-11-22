import { useState, useEffect, useRef } from 'react'
import './App.css'

function App() {
  const [timeline, setTimeline] = useState([])
  const [stats, setStats] = useState({
    steps: 0,
    maxSteps: 20,
    cumulativeReward: 0,
    status: 'idle'
  })
  const [currentThinking, setCurrentThinking] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [lastTimestamp, setLastTimestamp] = useState(0)
  const timelineEndRef = useRef(null)
  const pollingIntervalRef = useRef(null)

  const pollLogs = async () => {
    try {
      const response = await fetch(`http://localhost:8000/api/logs?since=${lastTimestamp}`)
      const data = await response.json()

      data.logs.forEach(log => {
        if (log.timestamp > lastTimestamp) {
          setLastTimestamp(log.timestamp)
        }

        const message = log.message

        // Parse thinking from logs
        if (message.includes('💭 THINKING:')) {
          const thinking = message.replace('💭 THINKING:', '').trim()
          setCurrentThinking(prev => ({ ...prev, thinking }))
        } else if (message.includes('⚡ ACTION:')) {
          const action = message.replace('⚡ ACTION:', '').trim()
          setCurrentThinking(prev => ({ ...prev, action }))
        } else if (message.includes('💉 PAYLOAD:')) {
          const payload = message.replace('💉 PAYLOAD:', '').trim()
          setCurrentThinking(prev => ({ ...prev, payload }))
        } else if (message.includes('🔮 EXPECTING:')) {
          const expecting = message.replace('🔮 EXPECTING:', '').trim()
          setCurrentThinking(prev => ({ ...prev, expecting }))
        } else if (message.includes('💰 REWARD:')) {
          // Parse reward and add to timeline
          const match = message.match(/💰 REWARD: ([-\d.]+) \((.+)\)/)
          if (match && currentThinking) {
            const reward = parseFloat(match[1])
            const reason = match[2]

            setTimeline(prev => [...prev, {
              step: prev.length + 1,
              thinking: currentThinking.thinking || 'No thinking provided',
              action: currentThinking.action || 'unknown',
              payload: currentThinking.payload,
              expecting: currentThinking.expecting,
              reward,
              reason,
              timestamp: new Date().toLocaleTimeString()
            }])

            setStats(prev => ({
              ...prev,
              steps: prev.steps + 1,
              cumulativeReward: prev.cumulativeReward + reward
            }))

            setCurrentThinking(null)
          }
        }

        // Check for status messages
        if (log.type === 'status') {
          if (log.message === 'starting') {
            setIsRunning(true)
            setStats(prev => ({ ...prev, status: 'running' }))
          } else if (log.message === 'completed' || log.message === 'failed') {
            setIsRunning(false)
            setStats(prev => ({ ...prev, status: log.message }))
          }
        }
      })
    } catch (error) {
      console.error('Error polling logs:', error)
    }
  }

  useEffect(() => {
    // Start polling when component mounts
    pollingIntervalRef.current = setInterval(pollLogs, 500) // Poll every 500ms

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [lastTimestamp, currentThinking])

  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [timeline])

  const runAgent = async () => {
    setTimeline([])
    setStats({ steps: 0, maxSteps: 20, cumulativeReward: 0, status: 'running' })
    setCurrentThinking(null)

    try {
      await fetch('http://localhost:8000/api/run/recon', { method: 'POST' })
    } catch (error) {
      console.error('Error running agent:', error)
    }
  }

  const resetAgent = async () => {
    if (!confirm('Clear all data and reset?')) return

    try {
      await fetch('http://localhost:8000/api/reset', { method: 'POST' })
      setTimeline([])
      setStats({ steps: 0, maxSteps: 20, cumulativeReward: 0, status: 'idle' })
      setCurrentThinking(null)
    } catch (error) {
      console.error('Error resetting:', error)
    }
  }

  const getRewardColor = (reward) => {
    if (reward >= 0.8) return 'reward-high'
    if (reward >= 0.3) return 'reward-medium'
    if (reward >= 0) return 'reward-low'
    return 'reward-negative'
  }

  return (
    <div className="app">
      <header className="header">
        <h1>🛡️ Security Agent</h1>
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-label">Steps</span>
            <span className="stat-value">{stats.steps}/{stats.maxSteps}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Reward</span>
            <span className="stat-value">{stats.cumulativeReward.toFixed(2)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Status</span>
            <span className={`stat-value status-${stats.status}`}>
              {stats.status === 'running' && '🔄 Running'}
              {stats.status === 'completed' && '✅ Complete'}
              {stats.status === 'failed' && '❌ Failed'}
              {stats.status === 'idle' && '⏸️ Idle'}
            </span>
          </div>
        </div>
      </header>

      <div className="controls">
        <button
          className="btn-primary"
          onClick={runAgent}
          disabled={isRunning}
        >
          {isRunning ? '⏳ Running...' : '▶️ Run Agent'}
        </button>
        <button
          className="btn-secondary"
          onClick={resetAgent}
          disabled={isRunning}
        >
          🗑️ Reset
        </button>
      </div>

      {currentThinking && (
        <div className="thinking-box">
          <h3>💭 Agent Thinking...</h3>
          <p className="thinking-text">{currentThinking.thinking}</p>
          {currentThinking.action && (
            <div className="thinking-action">
              <span className="label">Action:</span> {currentThinking.action}
            </div>
          )}
          {currentThinking.payload && (
            <div className="thinking-payload">
              <span className="label">Payload:</span> <code>{currentThinking.payload}</code>
            </div>
          )}
          {currentThinking.expecting && (
            <div className="thinking-expecting">
              <span className="label">Expecting:</span> {currentThinking.expecting}
            </div>
          )}
        </div>
      )}

      <div className="timeline">
        <h2>📊 Timeline</h2>
        {timeline.length === 0 ? (
          <div className="empty-state">
            <p>No steps yet. Click "Run Agent" to start.</p>
          </div>
        ) : (
          <div className="timeline-list">
            {timeline.map((item, i) => (
              <div key={i} className="timeline-item">
                <div className="timeline-header">
                  <span className="step-number">Step {item.step}</span>
                  <span className="timestamp">{item.timestamp}</span>
                </div>
                <div className="timeline-thinking">{item.thinking}</div>
                <div className="timeline-details">
                  <span className="action-badge">{item.action}</span>
                  {item.payload && <code className="payload-code">{item.payload}</code>}
                </div>
                <div className={`timeline-reward ${getRewardColor(item.reward)}`}>
                  <span className="reward-value">💰 {item.reward > 0 ? '+' : ''}{item.reward}</span>
                  <span className="reward-reason">{item.reason}</span>
                </div>
              </div>
            ))}
            <div ref={timelineEndRef} />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
