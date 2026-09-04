import { useEffect, useState } from 'react'

function pad(n) {
  return String(n).padStart(2, '0')
}

export function remainingMs(expiryUnix, nowMs = Date.now()) {
  if (!expiryUnix || expiryUnix <= 0) return 0
  return Math.max(0, expiryUnix * 1000 - nowMs)
}

export function formatRemaining(ms) {
  if (ms <= 0) {
    return { expired: true, text: 'Tugagan', days: 0, hours: 0, minutes: 0, seconds: 0 }
  }
  const total = Math.floor(ms / 1000)
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const clock = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
  return {
    expired: false,
    text: days > 0 ? `${days} kun  ${clock}` : clock,
    days,
    hours,
    minutes,
    seconds,
  }
}

export function useRemaining(expiryUnix, isFree) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (isFree || !expiryUnix) return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [expiryUnix, isFree])

  if (isFree) {
    return { active: true, free: true, ms: null, label: 'Cheksiz' }
  }

  const ms = remainingMs(expiryUnix, now)
  const formatted = formatRemaining(ms)
  return {
    active: ms > 0,
    free: false,
    ms,
    label: formatted.text,
    ...formatted,
  }
}
