import { useState, useEffect, useCallback } from 'react'

const POLL_INTERVAL = 3000 // 3 soniya

/**
 * LoginSession page — Mini-app orqali Telegram akkountini ulash.
 * 
 * Jarayon:
 *  1. "Ulash" bosilganda bot orqali xabar ketadi
 *  2. Foydalanuvchi botda "Sessiya Ulash" tugmasini bosadi
 *  3. Mini-app polling orqali sessiya ulanganini tekshirib turadi
 *  4. Sessiya ulangach — onConnected() chaqiriladi
 */
export default function LoginSession({ user, onConnected, onSkip }) {
  const [step, setStep] = useState('idle') // idle | requesting | waiting | connected | error
  const [errorMsg, setErrorMsg] = useState('')
  const [pollCount, setPollCount] = useState(0)

  // Polling — sessiya ulanganligi tekshiruvi
  const poll = useCallback(async () => {
    try {
      const res = await fetch('/api/login/check', {
        headers: buildHeaders()
      })
      const data = await res.json()
      if (data.has_session || data.status === 'connected') {
        setStep('connected')
        setTimeout(() => onConnected?.(), 1200)
      } else {
        setPollCount(c => c + 1)
      }
    } catch {
      // Polling xatosi — davom etaverar
    }
  }, [onConnected])

  useEffect(() => {
    let timer
    if (step === 'waiting') {
      timer = setInterval(poll, POLL_INTERVAL)
    }
    return () => clearInterval(timer)
  }, [step, poll])

  // Avvalgi holat yuklash
  useEffect(() => {
    fetch('/api/login/status', { headers: buildHeaders() })
      .then(r => r.json())
      .then(data => {
        if (data.has_session) {
          setStep('connected')
          setTimeout(() => onConnected?.(), 500)
        } else if (data.step === 'requested') {
          setStep('waiting')
        }
      })
      .catch(() => {})
  }, [onConnected])

  const handleRequest = async () => {
    setStep('requesting')
    setErrorMsg('')
    try {
      const res = await fetch('/api/login/request', {
        method: 'POST',
        headers: buildHeaders()
      })
      const data = await res.json()
      if (data.status === 'already_connected') {
        setStep('connected')
        setTimeout(() => onConnected?.(), 800)
      } else if (data.status === 'requested') {
        setStep('waiting')
      } else {
        setErrorMsg(data.message || 'Noma\'lum xatolik')
        setStep('error')
      }
    } catch (e) {
      setErrorMsg('Serverga ulanib bo\'lmadi')
      setStep('error')
    }
  }

  const handleLogout = async () => {
    try {
      await fetch('/api/login/session', {
        method: 'DELETE',
        headers: buildHeaders()
      })
    } catch {}
    setStep('idle')
  }

  return (
    <div style={{ padding: '20px 16px', maxWidth: 480, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <div style={{
          width: 72, height: 72,
          background: 'linear-gradient(135deg, #6c63ff, #a855f7)',
          borderRadius: 22,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 36, margin: '0 auto 16px',
          boxShadow: '0 8px 32px rgba(108,99,255,0.35)'
        }}>🔗</div>
        <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 8 }}>
          Sessiya Ulash
        </h2>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          Vento botining barcha funksiyalaridan foydalanish uchun Telegram akkauntingizni ulang.
        </p>
      </div>

      {/* Steps */}
      <div style={{
        display: 'flex', gap: 8, marginBottom: 28, justifyContent: 'center'
      }}>
        {['Bot orqali so\'rash', 'Botda tasdiqlash', 'Tayyor!'].map((label, i) => {
          const stepNum = ['idle', 'requesting', 'waiting', 'connected', 'error']
          const currentIdx = stepNum.indexOf(step)
          const done = (i === 0 && currentIdx >= 1) || (i === 1 && currentIdx >= 2) || (i === 2 && currentIdx >= 3)
          const active = (i === 0 && currentIdx === 0) || (i === 1 && currentIdx === 2) || (i === 2 && currentIdx === 3)
          return (
            <div key={i} style={{ textAlign: 'center', flex: 1 }}>
              <div style={{
                width: 32, height: 32, borderRadius: '50%',
                background: done ? 'linear-gradient(135deg, #6c63ff, #a855f7)' :
                  active ? 'rgba(108,99,255,0.2)' : 'rgba(255,255,255,0.07)',
                border: active ? '2px solid #6c63ff' : '2px solid transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 14, fontWeight: 700, margin: '0 auto 6px',
                color: done ? '#fff' : active ? '#6c63ff' : 'rgba(255,255,255,0.3)',
                transition: 'all 0.3s'
              }}>
                {done ? '✓' : i + 1}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.3 }}>{label}</div>
            </div>
          )
        })}
      </div>

      {/* Content per step */}
      {step === 'idle' && (
        <div style={{ animation: 'fadeIn 0.3s ease' }}>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
              <div style={{ fontSize: 28 }}>🤖</div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Bot orqali ulanish</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>
                  Telegram botimiz sizga xavfsiz sessiya ulash uchun ko'rsatmalar yuboradi.
                  Jarayon 1–2 daqiqa ichida tugaydi.
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {['🔒 100% xavfsiz — sessiya faqat sizning qurilmangizda', '⚡ Bir marta ulang, doim ishlaydi', '📱 Botda ko\'rsatmalarga amal qiling'].map((t, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>{t}</span>
                </div>
              ))}
            </div>
          </div>
          <button className="btn btn-primary" onClick={handleRequest} id="login-request-btn">
            🔗 Sessiyani Ulash
          </button>
          {onSkip && (
            <button className="btn btn-ghost" onClick={onSkip} style={{ marginTop: 10 }} id="login-skip-btn">
              Keyinroq ulash
            </button>
          )}
        </div>
      )}

      {step === 'requesting' && (
        <div style={{ textAlign: 'center', padding: '20px 0', animation: 'fadeIn 0.3s ease' }}>
          <div className="spinner" style={{ margin: '0 auto 16px' }} />
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>Bot orqali so'rov yuborilmoqda...</p>
        </div>
      )}

      {step === 'waiting' && (
        <div style={{ animation: 'fadeIn 0.3s ease' }}>
          <div className="card" style={{
            background: 'rgba(108,99,255,0.1)',
            border: '1px solid rgba(108,99,255,0.3)',
            marginBottom: 16, textAlign: 'center'
          }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📱</div>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>
              Botni oching!
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5 }}>
              <b style={{ color: '#fff' }}>@empire_family_bot</b> da "Sessiya Ulash" tugmasini bosing va ko'rsatmalarga amal qiling.
            </p>
            <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%',
                background: '#6c63ff',
                animation: 'pulse 1.5s infinite'
              }} />
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Kutilmoqda {pollCount > 0 ? `(${pollCount} marta tekshirildi)` : ''}
              </span>
            </div>
          </div>
          <a
            href="https://t.me/empire_family_bot"
            className="btn btn-primary"
            style={{ textDecoration: 'none', display: 'flex', marginBottom: 10 }}
            id="open-bot-btn"
          >
            🤖 Botni Telegramda Ochish
          </a>
          <button className="btn btn-ghost" onClick={() => setStep('idle')} id="login-back-btn">
            ← Orqaga
          </button>
        </div>
      )}

      {step === 'connected' && (
        <div style={{ textAlign: 'center', padding: '10px 0', animation: 'fadeIn 0.3s ease' }}>
          <div style={{
            width: 72, height: 72,
            background: 'linear-gradient(135deg, #22c55e, #16a34a)',
            borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 36, margin: '0 auto 16px',
            boxShadow: '0 8px 24px rgba(34,197,94,0.3)'
          }}>✓</div>
          <h3 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Sessiya Ulangan!</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
            Akkauntingiz muvaffaqiyatli ulandi. Barcha funksiyalar faol.
          </p>
          <button
            className="btn btn-danger"
            onClick={handleLogout}
            id="logout-session-btn"
            style={{ width: 'auto', padding: '10px 24px' }}
          >
            🔓 Sessiyani Uzish
          </button>
        </div>
      )}

      {step === 'error' && (
        <div style={{ animation: 'fadeIn 0.3s ease' }}>
          <div className="card" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', textAlign: 'center', marginBottom: 16 }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>⚠️</div>
            <p style={{ fontSize: 14, color: 'var(--danger)' }}>{errorMsg}</p>
          </div>
          <button className="btn btn-primary" onClick={handleRequest} id="login-retry-btn">
            🔄 Qayta Urinish
          </button>
          {onSkip && (
            <button className="btn btn-ghost" onClick={onSkip} style={{ marginTop: 10 }}>
              Keyinroq
            </button>
          )}
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }
      `}</style>
    </div>
  )
}

function buildHeaders() {
  const initData = window.Telegram?.WebApp?.initData || ''
  return {
    'Content-Type': 'application/json',
    'X-Init-Data': initData
  }
}
