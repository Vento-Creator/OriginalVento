import { useEffect, useState, useCallback } from 'react'
import { adminApi } from '../api'

// ─── Toast component ─────────────────────────────────────────────────────────
function Toast({ msg, type, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 2500)
    return () => clearTimeout(t)
  }, [onClose])
  return (
    <div className="toast-wrapper">
      <div className={`toast ${type === 'error' ? 'error' : ''}`}>{msg}</div>
    </div>
  )
}

// ─── UserDetailModal ─────────────────────────────────────────────────────────
function UserDetailModal({ userId, onClose, onAction }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [daysInput, setDaysInput] = useState('')
  const [acting, setActing] = useState(false)

  useEffect(() => {
    adminApi.getUserDetail(userId)
      .then(r => setData(r.data))
      .finally(() => setLoading(false))
  }, [userId])

  const refresh = () => {
    setLoading(true)
    adminApi.getUserDetail(userId)
      .then(r => setData(r.data))
      .finally(() => setLoading(false))
  }

  const handleExtend = async (days) => {
    setActing(true)
    try {
      await adminApi.extendSub(userId, days)
      onAction(`✅ ${days > 0 ? `+${days}` : days} kun muvaffaqiyatli qo'shildi`)
      refresh()
    } catch (e) {
      onAction(`❌ ${e.response?.data?.detail || 'Xatolik'}`, 'error')
    }
    setActing(false)
  }

  const handleCustomExtend = () => {
    const d = parseInt(daysInput)
    if (!d || d === 0) return
    handleExtend(d)
    setDaysInput('')
  }

  const handleToggleFree = async () => {
    setActing(true)
    try {
      await adminApi.toggleFree(userId, !data.is_free)
      onAction(data.is_free ? '✅ Bepul status olib tashlandi' : '✅ Bepul qilindi')
      refresh()
    } catch (e) {
      onAction(`❌ ${e.response?.data?.detail || 'Xatolik'}`, 'error')
    }
    setActing(false)
  }

  const handleBan = async () => {
    setActing(true)
    try {
      await adminApi.banUser(userId, !data.is_banned)
      onAction(data.is_banned ? '✅ Ban olib tashlandi' : '✅ Banlandi')
      refresh()
    } catch (e) {
      onAction(`❌ ${e.response?.data?.detail || 'Xatolik'}`, 'error')
    }
    setActing(false)
  }

  const name = data ? (data.first_name || data.username || 'Noma\'lum') : ''
  const expiryStr = data?.expiry_date && data.expiry_date > 0
    ? new Date(data.expiry_date * 1000).toLocaleString('uz-UZ', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      })
    : '—'

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      zIndex: 300, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
      animation: 'fadeIn 0.2s ease'
    }} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: 'var(--bg-secondary, #1a1a24)',
        borderRadius: '20px 20px 0 0',
        width: '100%', maxWidth: 480,
        maxHeight: '90vh', overflowY: 'auto',
        padding: '20px 16px 32px',
        animation: 'slideUp 0.3s ease'
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <div className="spinner" style={{ margin: '0 auto' }} />
          </div>
        ) : !data ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            Foydalanuvchi topilmadi
          </div>
        ) : (
          <>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700 }}>{name}</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {data.username ? `@${data.username}` : ''} • ID: {data.user_id}
                </p>
              </div>
              <button onClick={onClose} style={{
                background: 'rgba(255,255,255,0.1)', border: 'none',
                borderRadius: 8, padding: '6px 10px', color: '#fff',
                cursor: 'pointer', fontSize: 14
              }}>✕</button>
            </div>

            {/* Status badges */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
              {data.is_banned ? <span className="badge badge-danger">🚫 Banlangan</span> : null}
              {data.is_free ? <span className="badge badge-purple">♾️ Bepul</span> : null}
              {!data.is_banned && data.has_subscription ? <span className="badge badge-success">✅ Obuna faol</span> : null}
              {!data.is_banned && !data.is_free && !data.has_subscription ? <span className="badge badge-warning">❌ Obuna yo'q</span> : null}
            </div>

            {/* Info grid */}
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="list-item" style={{ borderBottom: '1px solid var(--card-border)' }}>
                <div className="item-left">
                  <div className="item-icon">📅</div>
                  <div>
                    <div className="item-title">Obuna tugashi</div>
                    <div className="item-sub">{expiryStr}</div>
                  </div>
                </div>
                <div style={{ fontWeight: 700, fontSize: 16, color: data.has_subscription ? 'var(--success)' : 'var(--danger)' }}>
                  {data.is_free ? '∞' : data.days_left > 0 ? `${data.days_left} kun` : '0'}
                </div>
              </div>
              <div className="list-item" style={{ borderBottom: '1px solid var(--card-border)' }}>
                <div className="item-left">
                  <div className="item-icon">💳</div>
                  <div>
                    <div className="item-title">To'lovlar soni</div>
                  </div>
                </div>
                <div className="item-value">{data.payment_count}</div>
              </div>
              <div className="list-item">
                <div className="item-left">
                  <div className="item-icon">🌐</div>
                  <div>
                    <div className="item-title">Til</div>
                  </div>
                </div>
                <div className="item-value">{data.language?.toUpperCase() || 'UZ'}</div>
              </div>
            </div>

            {/* Obuna boshqaruv */}
            <p className="section-title">Obuna boshqarish</p>
            <div className="card" style={{ marginBottom: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 12 }}>
                {[1, 7, 14, 30].map(d => (
                  <button key={d}
                    onClick={() => handleExtend(d)}
                    disabled={acting}
                    style={{
                      padding: '10px 4px', borderRadius: 8, border: '1px solid rgba(34,197,94,0.3)',
                      background: 'rgba(34,197,94,0.1)', color: 'var(--success)',
                      fontWeight: 600, fontSize: 12, cursor: 'pointer', transition: 'all 0.2s'
                    }}>
                    +{d} kun
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="number"
                  className="input"
                  placeholder="Kunlar (masalan: 60 yoki -5)"
                  value={daysInput}
                  onChange={e => setDaysInput(e.target.value)}
                  style={{ flex: 1, margin: 0 }}
                  id="admin-days-input"
                />
                <button
                  onClick={handleCustomExtend}
                  disabled={acting || !daysInput}
                  className="btn btn-primary"
                  style={{ width: 'auto', padding: '10px 16px', fontSize: 13 }}
                  id="admin-extend-btn"
                >
                  ➕
                </button>
              </div>
            </div>

            {/* Boshqa harakatlar */}
            <p className="section-title">Boshqaruv</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button
                onClick={handleToggleFree}
                disabled={acting}
                className={data.is_free ? 'btn btn-ghost' : 'btn btn-primary'}
                style={{ fontSize: 13, padding: '12px 16px' }}
                id="admin-toggle-free-btn"
              >
                {data.is_free ? '🔓 Bepul statusni olib tashlash' : '♾️ Bepul qilish (cheksiz)'}
              </button>
              <button
                onClick={handleBan}
                disabled={acting}
                className={data.is_banned ? 'btn btn-ghost' : 'btn btn-danger'}
                style={{ fontSize: 13, padding: '12px 16px' }}
                id="admin-ban-btn"
              >
                {data.is_banned ? '🔓 Bandan chiqarish' : '🚫 Banlash'}
              </button>
            </div>

            {/* So'nggi to'lovlar */}
            {data.recent_payments?.length > 0 && (
              <>
                <p className="section-title" style={{ marginTop: 16 }}>So'nggi to'lovlar</p>
                <div className="card">
                  {data.recent_payments.map((p, i) => (
                    <div key={i} className="list-item">
                      <div className="item-left">
                        <div className="item-icon">💳</div>
                        <div>
                          <div className="item-title">{p.amount} {p.currency}</div>
                          <div className="item-sub">
                            {new Date((p.created_at || 0) * 1000).toLocaleDateString('uz-UZ')}
                          </div>
                        </div>
                      </div>
                      <span className={`badge ${p.status === 'paid' ? 'badge-success' : 'badge-warning'}`}>
                        {p.status === 'paid' ? "To'langan" : p.status}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(100%); }
          to   { transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}

// ─── AdminPanel ──────────────────────────────────────────────────────────────
export default function AdminPanel({ user }) {
  const [stats, setStats] = useState(null)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('stats')
  const [search, setSearch] = useState('')
  const [searchTimeout, setSearchTimeout] = useState(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [selectedUserId, setSelectedUserId] = useState(null)
  const [toast, setToast] = useState(null)
  const limit = 20

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
  }

  const loadUsers = useCallback((p = 1, q = '') => {
    adminApi.getUsers(p, limit, q)
      .then(r => {
        setUsers(r.data.users)
        setTotal(r.data.total)
        setPage(r.data.page)
      })
  }, [])

  useEffect(() => {
    Promise.all([adminApi.getStats(), adminApi.getUsers(1, limit)])
      .then(([sRes, uRes]) => {
        setStats(sRes.data)
        setUsers(uRes.data.users)
        setTotal(uRes.data.total)
      })
      .finally(() => setLoading(false))
  }, [])

  // Search debounce
  const handleSearch = (val) => {
    setSearch(val)
    if (searchTimeout) clearTimeout(searchTimeout)
    setSearchTimeout(setTimeout(() => {
      loadUsers(1, val)
    }, 400))
  }

  const handleAction = (msg, type = 'success') => {
    showToast(msg, type)
    // Refresh users list
    loadUsers(page, search)
  }

  if (loading) return (
    <div className="page" style={{ textAlign: 'center', paddingTop: 60 }}>
      <div className="spinner" style={{ margin: '0 auto' }} />
    </div>
  )

  const totalPages = Math.ceil(total / limit)

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
            id={`admin-tab-${t}`}
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
        <>
          {/* Search */}
          <div style={{ marginBottom: 12 }}>
            <input
              className="input"
              placeholder="🔍 Qidirish: ism, username yoki ID"
              value={search}
              onChange={e => handleSearch(e.target.value)}
              id="admin-search"
              style={{ margin: 0 }}
            />
          </div>

          {/* Total count */}
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
            Jami: {total} foydalanuvchi {search && `("${search}" uchun)`}
          </p>

          <div className="card">
            {users.length === 0 && (
              <p style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 20 }}>Foydalanuvchilar topilmadi</p>
            )}
            {users.map(u => (
              <div
                key={u.user_id}
                className="list-item"
                onClick={() => setSelectedUserId(u.user_id)}
                style={{ cursor: 'pointer', transition: 'background 0.2s', borderRadius: 8, padding: '14px 8px', margin: '0 -8px' }}
                onMouseOver={e => e.currentTarget.style.background = 'rgba(108,99,255,0.08)'}
                onMouseOut={e => e.currentTarget.style.background = 'transparent'}
              >
                <div className="item-left">
                  <div className="item-icon" style={{ fontSize: 16 }}>
                    {u.is_banned ? '🚫' : u.is_free ? '♾️' : u.has_subscription ? '✅' : '⭕'}
                  </div>
                  <div>
                    <div className="item-title">
                      {u.first_name || u.username || 'Noma\'lum'}
                      {u.username ? ` @${u.username}` : ''}
                    </div>
                    <div className="item-sub">
                      ID: {u.user_id} • {u.is_free ? '♾️ Bepul' : u.days_left > 0 ? `${u.days_left} kun` : 'Tugagan'}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {u.is_banned && <span className="badge badge-danger" style={{ fontSize: 10, padding: '2px 6px' }}>Ban</span>}
                  {!u.is_banned && u.is_free && <span className="badge badge-purple" style={{ fontSize: 10, padding: '2px 6px' }}>Bepul</span>}
                  {!u.is_banned && !u.is_free && u.has_subscription && <span className="badge badge-success" style={{ fontSize: 10, padding: '2px 6px' }}>Faol</span>}
                  {!u.is_banned && !u.is_free && !u.has_subscription && <span className="badge badge-warning" style={{ fontSize: 10, padding: '2px 6px' }}>—</span>}
                  <span style={{ fontSize: 14, color: 'var(--text-muted)' }}>›</span>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 16 }}>
              <button
                onClick={() => { setPage(p => p - 1); loadUsers(page - 1, search) }}
                disabled={page <= 1}
                className="btn btn-ghost"
                style={{ width: 'auto', padding: '8px 16px', fontSize: 12, opacity: page <= 1 ? 0.3 : 1 }}
              >
                ← Oldingi
              </button>
              <span style={{ display: 'flex', alignItems: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
                {page} / {totalPages}
              </span>
              <button
                onClick={() => { setPage(p => p + 1); loadUsers(page + 1, search) }}
                disabled={page >= totalPages}
                className="btn btn-ghost"
                style={{ width: 'auto', padding: '8px 16px', fontSize: 12, opacity: page >= totalPages ? 0.3 : 1 }}
              >
                Keyingi →
              </button>
            </div>
          )}
        </>
      )}

      {/* User Detail Modal */}
      {selectedUserId && (
        <UserDetailModal
          userId={selectedUserId}
          onClose={() => setSelectedUserId(null)}
          onAction={handleAction}
        />
      )}

      {/* Toast */}
      {toast && <Toast msg={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  )
}
