import { useRemaining } from '../utils/subscription'

export default function Profile({ user }) {
  const tg = window.Telegram?.WebApp
  const remaining = useRemaining(user?.subscription_expiry, user?.is_free)

  const name = [user?.first_name, user?.last_name].filter(Boolean).join(' ')
  const username = user?.username ? `@${user.username}` : '—'

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
        <div style={{ marginTop: 12 }}>
          {remaining.active
            ? <span className="badge badge-success">✅ Obuna faol</span>
            : <span className="badge badge-danger">❌ Obuna yo'q</span>
          }
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

      {/* Close button */}
      <button
        className="btn btn-ghost"
        onClick={() => tg?.close()}
        style={{ marginTop: 8 }}
      >
        ✕ Yopish
      </button>
    </div>
  )
}
