import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
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


export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    const load = () => {
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

  if (loading) return <LoadingScreen />
  
  if (error) {
    const isAuthError = error.includes("X-Init-Data") || error.includes("initData") || error.includes("imzosi")
    
    if (isAuthError) {
      return <LandingPage />
    }
    
    return (
      <div className="error-screen" style={{ padding: '40px 24px' }}>
        <div className="error-icon">⚠️</div>
        <p>{error}</p>
        <button className="btn btn-ghost" style={{ marginTop: 16 }} onClick={() => window.location.reload()}>Qayta urinish</button>
      </div>
    )
  }

  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Dashboard user={user} />} />
        <Route path="/profile" element={<Profile user={user} />} />
        <Route path="/subscription" element={<Subscription user={user} />} />
        <Route path="/commands" element={<Commands user={user} />} />
        <Route path="/stats" element={<Stats user={user} />} />
        {user?.is_admin && <Route path="/admin" element={<AdminPanel user={user} />} />}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
      <NavBar user={user} />
    </div>
  )
}
