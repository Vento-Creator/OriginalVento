import { Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useRemaining } from '../utils/subscription'
import { loginApi } from '../api'

export default function Dashboard({ user, onStartLogin }) {
  const remaining = useRemaining(user?.subscription_expiry, user?.is_free)
  const hasSub = remaining.active
  const canPurchase = !user?.is_free && !hasSub
  const name = user?.first_name || 'Foydalanuvchi'
  const [sessionStatus, setSessionStatus] = useState(null)

  useEffect(() => {
    loginApi.status()
      .then(r => setSessionStatus(r.data))
      .catch(() => {})
  }, [])

  return (
    <div className="page">
      <div className="hero-card">
        {user?.photo_url
          ? <img src={user.photo_url} alt="avatar" className="avatar" />
          : <div className="avatar-placeholder">👤</div>
        }
        <h2>Salom, {name}! 👋</h2>
        <p className="sub-text">Vento Mini App ga xush kelibsiz</p>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {hasSub
            ? <span className="badge badge-success">✅ Obuna faol</span>
            : <span className="badge badge-danger">❌ Obuna yo'q</span>
          }
          {sessionStatus?.has_session === true && (
            <span className="badge badge-success">🔗 Sessiya ulangan</span>
          )}
          {sessionStatus?.has_session === false && (
            <span className="badge badge-warning">⚠️ Sessiya yo'q</span>
          )}
          {user?.is_admin && (
            <span className="badge badge-purple" style={{ marginLeft: 4 }}>🛠 Admin</span>
          )}
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value countdown">{hasSub ? remaining.label : '—'}</div>
          <div className="stat-label">{remaining.free ? 'Obuna' : 'Qolgan vaqt'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{hasSub ? '✓' : '✗'}</div>
          <div className="stat-label">Holat</div>
        </div>
      </div>

      {/* Sessiya ogohlantiruvi */}
      {sessionStatus?.has_session === false && (
        <div className="card" style={{
          background: 'rgba(245,158,11,0.1)',
          border: '1px solid rgba(245,158,11,0.3)',
          marginBottom: 16
        }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <div style={{ fontSize: 24, flexShrink: 0 }}>⚠️</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 14 }}>
                Sessiya ulanmagan
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.4 }}>
                Bot funksiyalari (UTag, Taymer va boshqalar) to'liq ishlashi uchun
                Telegram akkauntingizni ulang.
              </p>
              <button
                className="btn btn-primary"
                onClick={onStartLogin}
                id="dashboard-connect-btn"
                style={{ padding: '10px 20px', fontSize: 13 }}
              >
                🔗 Sessiya Ulash
              </button>
            </div>
          </div>
        </div>
      )}

      <p className="section-title">Tezkor harakatlar</p>
      <div className="quick-actions">
        <Link to="/subscription" className="action-btn" id="action-subscription">
          <div className="action-icon">⭐</div>
          <div className="action-label">Obuna</div>
        </Link>
        <Link to="/commands" className="action-btn" id="action-commands">
          <div className="action-icon">⌨️</div>
          <div className="action-label">Komandalar</div>
        </Link>
        <Link to="/stats" className="action-btn" id="action-stats">
          <div className="action-icon">📊</div>
          <div className="action-label">Statistika</div>
        </Link>
        <Link to="/profile" className="action-btn" id="action-profile">
          <div className="action-icon">👤</div>
          <div className="action-label">Profil</div>
        </Link>
        {sessionStatus?.has_session === false && (
          <button
            onClick={onStartLogin}
            className="action-btn"
            id="action-session"
            style={{ border: '1px solid rgba(245,158,11,0.4)', background: 'rgba(245,158,11,0.08)', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            <div className="action-icon">🔗</div>
            <div className="action-label" style={{ color: 'var(--warning)' }}>Sessiya</div>
          </button>
        )}
        {user?.is_admin && (
          <Link to="/admin" className="action-btn" id="action-admin">
            <div className="action-icon">🛠</div>
            <div className="action-label">Admin</div>
          </Link>
        )}
      </div>

      {canPurchase && (
        <div className="card card-gradient">
          <p style={{ fontWeight: 600, marginBottom: 8 }}>⭐ Obuna faollashtiring</p>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
            30 kunlik obuna uchun 100 Telegram Stars to'lang va barcha imkoniyatlardan foydalaning.
          </p>
          <Link to="/subscription">
            <button className="btn btn-primary" id="dashboard-subscribe-btn">Obuna sotib olish</button>
          </Link>
        </div>
      )}
    </div>
  )
}
