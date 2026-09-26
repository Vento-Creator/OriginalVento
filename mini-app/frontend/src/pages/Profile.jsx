import { useState, useEffect } from 'react'
import { useRemaining } from '../utils/subscription'
import { loginApi } from '../api'

export default function Profile({ user, onStartLogin }) {
  const tg = window.Telegram?.WebApp
  const remaining = useRemaining(user?.subscription_expiry, user?.is_free)
  const [sessionStatus, setSessionStatus] = useState(null)
  const [loadingSession, setLoadingSession] = useState(true)

  const name = [user?.first_name, user?.last_name].filter(Boolean).join(' ')
  const username = user?.username ? `@${user.username}` : '—'

  useEffect(() => {
    loginApi.status()
      .then(r => setSessionStatus(r.data))
      .catch(() => setSessionStatus(null))
      .finally(() => setLoadingSession(false))
  }, [])

  const handleLogout = () => {
    if (tg) {
      tg.showConfirm(
        '🔓 Sessiyani uzmoqchimisiz?\n\nUzilgandan so\'ng bot funksiyalari ishlashni to\'xtatadi.',
        async (confirmed) => {
          if (confirmed) {
            await loginApi.logout().catch(() => {})
            setSessionStatus({ has_session: false, step: 'idle' })
          }
        }
      )
    } else {
      loginApi.logout().then(() => {
        setSessionStatus({ has_session: false, step: 'idle' })
      })
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Profil</h1>
      </div>

      {/* Avatar + name */}
      <div className="card" style={{ textAlign: 'center', padding: '28px 20px' }}>
        {user?.photo_url
          ? <img src={user.photo_url} alt="avatar" style={{ width: 80, height: 80, borderRadius: '50%', border: '3px solid var(--accent)', marginBottom: 12, objectFit: 'cover' }} />
          : <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'linear-gradient(135deg,var(--accent),var(--accent-2))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36, margin: '0 auto 12px' }}>👤</div>
        }
        <h2 style={{ fontSize: 20, fontWeight: 700 }}>{name || 'Foydalanuvchi'}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 14, marginTop: 4 }}>{username}</p>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
          {remaining.active
            ? <span className="badge badge-success">✅ Obuna faol</span>
            : <span className="badge badge-danger">❌ Obuna yo'q</span>
          }
          {user?.is_admin && (
            <span className="badge badge-purple">🛠 Admin</span>
          )}
        </div>
        {remaining.active && !remaining.free && (
          <p className="countdown" style={{ marginTop: 10, fontSize: 18 }}>{remaining.label}</p>
        )}
      </div>

      {/* Info */}
      <div className="card">
        <div className="list-item">
          <div className="item-left">
            <div className="item-icon">🆔</div>
            <div>
              <div className="item-title">Telegram ID</div>
              <div className="item-sub">Sizning noyob identifikatoringiz</div>
            </div>
          </div>
          <div className="item-value" style={{ fontFamily: 'monospace' }}>{user?.id}</div>
        </div>

        <div className="list-item">
          <div className="item-left">
            <div className="item-icon">🌐</div>
            <div>
              <div className="item-title">Til</div>
            </div>
          </div>
          <div className="item-value">{user?.language_code?.toUpperCase() || 'UZ'}</div>
        </div>

        <div className="list-item">
          <div className="item-left">
            <div className="item-icon">📅</div>
            <div>
              <div className="item-title">Obuna tugash sanasi</div>
            </div>
          </div>
          <div className="item-value">
            {user?.is_free
              ? 'Cheksiz'
              : user?.subscription_expiry && user.subscription_expiry > 0
                ? new Date(user.subscription_expiry * 1000).toLocaleString('uz-UZ')
                : '—'
            }
          </div>
        </div>

        {user?.is_admin && (
          <div className="list-item">
            <div className="item-left">
              <div className="item-icon">🛠</div>
              <div>
                <div className="item-title">Admin huquqlari</div>
              </div>
            </div>
            <span className="badge badge-purple">Faol</span>
          </div>
        )}
      </div>

      {/* Sessiya holati */}
      <p className="section-title">Telegram Sessiya</p>
      <div className="card" style={{ marginBottom: 16 }}>
        {loadingSession ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="spinner" style={{ width: 20, height: 20, borderWidth: 2 }} />
            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Tekshirilmoqda...</span>
          </div>
        ) : sessionStatus?.has_session ? (
          <div>
            <div className="list-item" style={{ paddingTop: 0 }}>
              <div className="item-left">
                <div className="item-icon">🔗</div>
                <div>
                  <div className="item-title">Sessiya ulangan</div>
                  <div className="item-sub">Bot funksiyalari faol ishlayapti</div>
                </div>
              </div>
              <span className="badge badge-success">Faol</span>
            </div>
            <button
              className="btn btn-danger"
              onClick={handleLogout}
              id="profile-logout-btn"
              style={{ marginTop: 12 }}
            >
              🔓 Sessiyani Uzish
            </button>
          </div>
        ) : (
          <div>
            <div className="list-item" style={{ paddingTop: 0 }}>
              <div className="item-left">
                <div className="item-icon">⚠️</div>
                <div>
                  <div className="item-title">Sessiya yo'q</div>
                  <div className="item-sub">Bot funksiyalari ishlamasligi mumkin</div>
                </div>
              </div>
              <span className="badge badge-warning">Ulanmagan</span>
            </div>
            <button
              className="btn btn-primary"
              onClick={onStartLogin}
              id="profile-connect-btn"
              style={{ marginTop: 12 }}
            >
              🔗 Sessiya Ulash
            </button>
          </div>
        )}
      </div>

      {/* Close button */}
      <button
        className="btn btn-ghost"
        onClick={() => tg?.close()}
        style={{ marginTop: 4 }}
        id="profile-close-btn"
      >
        ✕ Yopish
      </button>
    </div>
  )
}
