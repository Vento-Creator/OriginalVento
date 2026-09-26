import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useState, useEffect, useRef, useCallback } from 'react'
import { usersApi } from './api'
import NavBar from './components/NavBar'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import Subscription from './pages/Subscription'
import Commands from './pages/Commands'
import Stats from './pages/Stats'
import AdminPanel from './pages/AdminPanel'
import LoadingScreen from './components/LoadingScreen'
import LandingPage from './pages/LandingPage'
import LoginSession from './pages/LoginSession'

// ─── Chala jarayon ogohlantiruvi ──────────────────────────────────────────────
function useLoginGuard(loginInProgress) {
  useEffect(() => {
    if (!loginInProgress) return

    // beforeunload — brauzer sahifasini yopmoqchi bo'lganda
    const handleBeforeUnload = (e) => {
      const msg = 'Login jarayoni tugallanmagan! Sahifani yopsangiz ma\'lumot saqlanmaydi.'
      e.preventDefault()
      e.returnValue = msg
      return msg
    }

    // Telegram WebApp backButton — foydalanuvchi orqaga bosmochoq bo'lsa
    const tg = window.Telegram?.WebApp
    if (tg?.BackButton) {
      tg.BackButton.show()
      tg.BackButton.onClick(() => {
        tg.showConfirm(
          '⚠️ Login jarayoni tugallanmagan!\n\nSahifani yopsangiz ma\'lumot saqlanmaydi va keyingi safar tozadan boshlashingiz kerak bo\'ladi. Davom etasizmi?',
          (confirmed) => {
            if (confirmed) {
              tg.BackButton.hide()
              // Jarayonni tozalash — localStorage dan o'chirish
              localStorage.removeItem('login_in_progress')
              tg.close()
            }
          }
        )
      })
    }

    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      if (tg?.BackButton) {
        tg.BackButton.hide()
        tg.BackButton.offClick()
      }
    }
  }, [loginInProgress])
}


export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showLogin, setShowLogin] = useState(false)
  const [loginInProgress, setLoginInProgress] = useState(false)

  // Chala login ogohlantiruvi
  useLoginGuard(loginInProgress)

  const loadUser = useCallback(() => {
    return usersApi.getMe()
      .then(r => {
        if (typeof r.data === 'string' && r.data.includes('<!doctype html>')) {
          throw new Error("Backend tizimiga ulanib bo'lmadi (API URL xatosi)")
        }
        setUser(r.data)
        setError(null)
        return r.data
      })
      .catch(e => {
        const msg = e.response?.data?.detail || e.message || 'Xatolik yuz berdi'
        setError(msg)
        throw e
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    let cancelled = false

    const load = () => {
      setLoading(true)
      usersApi.getMe()
        .then(r => {
          if (cancelled) return
          if (typeof r.data === 'string' && r.data.includes('<!doctype html>')) {
            throw new Error("Backend tizimiga ulanib bo'lmadi (API URL xatosi)")
          }
          setUser(r.data)
          setError(null)
        })
        .catch(e => {
          if (!cancelled) setError(e.response?.data?.detail || e.message || 'Xatolik yuz berdi')
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }

    load()

    const onVisible = () => {
      if (document.visibilityState === 'visible') load()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  // Login jarayonini boshlash
  const handleStartLogin = () => {
    localStorage.setItem('login_in_progress', '1')
    setLoginInProgress(true)
    setShowLogin(true)
  }

  // Login tugallandi
  const handleLoginConnected = () => {
    localStorage.removeItem('login_in_progress')
    setLoginInProgress(false)
    setShowLogin(false)
    setLoading(true)
    loadUser()
  }

  // Login o'tkazib yuborish (keyinroq)
  const handleLoginSkip = () => {
    const tg = window.Telegram?.WebApp
    if (loginInProgress && tg) {
      tg.showConfirm(
        '⚠️ Login jarayoni tugallanmagan!\n\nKeyingi safar tozadan boshlashingiz kerak bo\'ladi. Davom etasizmi?',
        (confirmed) => {
          if (confirmed) {
            localStorage.removeItem('login_in_progress')
            setLoginInProgress(false)
            setShowLogin(false)
          }
        }
      )
    } else {
      localStorage.removeItem('login_in_progress')
      setLoginInProgress(false)
      setShowLogin(false)
    }
  }

  if (loading) return <LoadingScreen />

  // Auth xatolik — LandingPage ko'rsatish
  if (error) {
    const isAuthError = error.includes("X-Init-Data") ||
      error.includes("initData") ||
      error.includes("imzosi") ||
      error.includes("401")

    if (isAuthError) {
      return <LandingPage />
    }

    return (
      <div className="error-screen" style={{ padding: '40px 24px' }}>
        <div className="error-icon">⚠️</div>
        <p style={{ marginBottom: 8 }}>{error}</p>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
          Backend serveriga ulanishda muammo yuz berdi.
        </p>
        <button className="btn btn-ghost" style={{ marginTop: 8, width: 'auto', padding: '12px 24px' }}
          onClick={() => window.location.reload()}>
          🔄 Qayta urinish
        </button>
      </div>
    )
  }

  // Login sahifasi
  if (showLogin) {
    return (
      <div className="app">
        <LoginSession
          user={user}
          onConnected={handleLoginConnected}
          onSkip={handleLoginSkip}
        />
      </div>
    )
  }

  return (
    <div className="app">
      <Routes>
        <Route path="/" element={
          <Dashboard
            user={user}
            onStartLogin={handleStartLogin}
          />
        } />
        <Route path="/profile" element={
          <Profile
            user={user}
            onStartLogin={handleStartLogin}
          />
        } />
        <Route path="/subscription" element={<Subscription user={user} />} />
        <Route path="/commands" element={<Commands user={user} />} />
        <Route path="/stats" element={<Stats user={user} />} />
        {user?.is_admin && (
          <Route path="/admin" element={<AdminPanel user={user} />} />
        )}
        <Route path="/login" element={
          <LoginSession
            user={user}
            onConnected={handleLoginConnected}
            onSkip={handleLoginSkip}
          />
        } />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
      <NavBar user={user} />
    </div>
  )
}
