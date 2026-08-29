import { useEffect, useState } from 'react'
import { statsApi } from '../api'

export default function Stats({ user }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    statsApi.get().then(r => setData(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="page" style={{ textAlign: 'center', paddingTop: 60 }}>
      <div className="spinner" style={{ margin: '0 auto' }} />
    </div>
  )

  return (
    <div className="page">
      <div className="page-header">
        <h1>📊 Statistika</h1>
      </div>

      {/* Stat grid */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value">{data?.active_timer_count || 0}</div>
          <div className="stat-label">Faol taymerlar</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data?.scraped_groups || 0}</div>
          <div className="stat-label">Scraped guruhlar</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data?.scraped_members || 0}</div>
          <div className="stat-label">Scraped a'zolar</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data?.stars_spent || 0}</div>
          <div className="stat-label">Stars sarflangan</div>
        </div>
      </div>

      {/* Active timers */}
      {data?.active_timers?.length > 0 && (
        <>
          <p className="section-title">Faol taymerlar</p>
          <div className="card">
            {data.active_timers.map((t, i) => (
              <div key={i} className="list-item">
                <div className="item-left">
                  <div className="item-icon">⏱</div>
                  <div>
                    <div className="item-title" style={{ fontFamily: 'monospace', fontSize: 13 }}>
                      {String(t.chat_id)}
                    </div>
                    <div className="item-sub">
                      Har {t.interval_minutes} daqiqada • {t.message_text?.slice(0, 30)}...
                    </div>
                  </div>
                </div>
                <span className="badge badge-success">Faol</span>
              </div>
            ))}
          </div>
        </>
      )}

      {data?.active_timer_count === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '32px 20px' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⏱</div>
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>Hozircha faol taymerlar yo'q</p>
        </div>
      )}
    </div>
  )
}
