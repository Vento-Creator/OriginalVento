import { Link } from 'react-router-dom'

export default function Dashboard({ user }) {
  const daysLeft = user?.days_left || 0
  const hasSub = user?.has_subscription
  const name = user?.first_name || 'Foydalanuvchi'

  return (
    <div className="page">
      {/* Hero */}
      <div className="hero-card">
        {user?.photo_url
          ? <img src={user.photo_url} alt="avatar" className="avatar" />
          : <div className="avatar-placeholder">👤</div>
        }
        <h2>Salom, {name}! 👋</h2>
        <p className="sub-text">Vento Mini App ga xush kelibsiz</p>
        <div style={{ marginTop: 12 }}>
          {hasSub
            ? <span className="badge badge-success">✅ Faol — {daysLeft} kun</span>
            : <span className="badge badge-danger">❌ Obuna yo'q</span>
          }
          {user?.is_admin && (
            <span className="badge badge-purple" style={{ marginLeft: 8 }}>🛠 Admin</span>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value">{daysLeft}</div>
          <div className="stat-label">Kun qoldi</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{user?.is_free ? '∞' : (hasSub ? '✓' : '✗')}</div>
          <div className="stat-label">Obuna holati</div>
        </div>
      </div>

      {/* Quick Actions */}
      <p className="section-title">Tezkor harakatlar</p>
      <div className="quick-actions">
        <Link to="/subscription" className="action-btn">
          <div className="action-icon">⭐</div>
          <div className="action-label">Obuna</div>
        </Link>
        <Link to="/commands" className="action-btn">
          <div className="action-icon">⌨️</div>
          <div className="action-label">Komandalar</div>
        </Link>
        <Link to="/stats" className="action-btn">
          <div className="action-icon">📊</div>
          <div className="action-label">Statistika</div>
        </Link>
        <Link to="/profile" className="action-btn">
          <div className="action-icon">👤</div>
          <div className="action-label">Profil</div>
        </Link>
        {user?.is_admin && (
          <Link to="/admin" className="action-btn">
            <div className="action-icon">🛠</div>
            <div className="action-label">Admin</div>
          </Link>
        )}
      </div>

      {/* Info */}
      {!hasSub && (
        <div className="card card-gradient">
          <p style={{ fontWeight: 600, marginBottom: 8 }}>⭐ Obuna faollashtiring</p>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
            30 kunlik obuna uchun 100 Telegram Stars to'lang va barcha imkoniyatlardan foydalaning.
          </p>
          <Link to="/subscription">
            <button className="btn btn-primary">Obuna sotib olish</button>
          </Link>
        </div>
      )}
    </div>
  )
}
