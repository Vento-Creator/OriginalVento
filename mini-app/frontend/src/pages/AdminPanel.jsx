import { useEffect, useState } from 'react'
import { adminApi } from '../api'

export default function AdminPanel({ user }) {
  const [stats, setStats] = useState(null)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('stats')

  useEffect(() => {
    Promise.all([adminApi.getStats(), adminApi.getUsers()])
      .then(([sRes, uRes]) => {
        setStats(sRes.data)
        setUsers(uRes.data.users)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="page" style={{ textAlign: 'center', paddingTop: 60 }}>
      <div className="spinner" style={{ margin: '0 auto' }} />
    </div>
  )

  return (
    <div className="page">
      <div className="page-header">
        <h1>🛠 Admin Panel</h1>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {['stats', 'users'].map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              flex: 1, padding: '10px', borderRadius: 10, border: 'none',
              background: tab === t ? 'var(--accent)' : 'var(--card-bg)',
              color: tab === t ? '#fff' : 'var(--text-muted)',
              fontWeight: 600, cursor: 'pointer', fontSize: 13,
              transition: 'all 0.2s'
            }}
          >
            {t === 'stats' ? '📊 Statistika' : '👥 Foydalanuvchilar'}
          </button>
        ))}
      </div>

      {tab === 'stats' && stats && (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.total_users}</div>
              <div className="stat-label">Jami foydalanuvchi</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.active_subscriptions}</div>
              <div className="stat-label">Faol obunalar</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.free_users}</div>
              <div className="stat-label">Bepul foydalanuvchi</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.banned_users}</div>
              <div className="stat-label">Banlangan</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.total_payments}</div>
              <div className="stat-label">Jami to'lovlar</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">⭐{stats.total_stars_earned}</div>
              <div className="stat-label">Stars daromad</div>
            </div>
          </div>
        </>
      )}

      {tab === 'users' && (
        <div className="card">
          {users.length === 0 && (
            <p style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 20 }}>Foydalanuvchilar topilmadi</p>
          )}
          {users.map(u => (
            <div key={u.user_id} className="list-item">
              <div className="item-left">
                <div className="item-icon" style={{ fontSize: 16 }}>
                  {u.is_banned ? '🚫' : u.is_free ? '♾️' : u.has_subscription ? '✅' : '⭕'}
                </div>
                <div>
                  <div className="item-title">
                    {u.first_name || u.username || 'Noma\'lum'}
                    {u.username ? ` @${u.username}` : ''}
                  </div>
                  <div className="item-sub">ID: {u.user_id} • {u.days_left} kun</div>
                </div>
              </div>
              {u.is_banned && <span className="badge badge-danger">Ban</span>}
              {!u.is_banned && u.is_free && <span className="badge badge-purple">Bepul</span>}
              {!u.is_banned && !u.is_free && u.has_subscription && <span className="badge badge-success">Faol</span>}
              {!u.is_banned && !u.is_free && !u.has_subscription && <span className="badge badge-warning">Tugagan</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
