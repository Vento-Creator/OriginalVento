import { useEffect, useState } from 'react'
import { commandsApi } from '../api'

function Toast({ msg, type }) {
  if (!msg) return null
  return (
    <div className="toast-wrapper">
      <div className={`toast${type === 'error' ? ' error' : ''}`}>{msg}</div>
    </div>
  )
}

export default function Commands({ user }) {
  const [cmds, setCmds] = useState({})
  const [edits, setEdits] = useState({})
  const [saving, setSaving] = useState({})
  const [toast, setToast] = useState({ msg: '', type: '' })

  useEffect(() => {
    commandsApi.get().then(r => {
      setCmds(r.data.commands)
      setEdits(r.data.commands)
    })
  }, [])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast({ msg: '', type: '' }), 2500)
  }

  const save = async (cmd) => {
    const value = edits[cmd]?.trim()
    if (!value || value === cmds[cmd]) return
    setSaving(s => ({ ...s, [cmd]: true }))
    try {
      await commandsApi.update(cmd, value)
      setCmds(c => ({ ...c, [cmd]: value }))
      showToast(`✅ "${cmd}" yangilandi`)
    } catch (e) {
      showToast(e.response?.data?.detail || 'Xatolik', 'error')
    } finally {
      setSaving(s => ({ ...s, [cmd]: false }))
    }
  }

  const reset = async (cmd) => {
    setSaving(s => ({ ...s, [cmd]: true }))
    try {
      const r = await commandsApi.reset(cmd)
      const def = r.data.reset_to
      setCmds(c => ({ ...c, [cmd]: def }))
      setEdits(e => ({ ...e, [cmd]: def }))
      showToast(`🔄 "${cmd}" aslga qaytarildi`)
    } catch (e) {
      showToast(e.response?.data?.detail || 'Xatolik', 'error')
    } finally {
      setSaving(s => ({ ...s, [cmd]: false }))
    }
  }

  const CMDS = ['atag', 'stop', 'pause', 'resume']
  const ICONS = { atag: '🏷', stop: '🛑', pause: '⏸', resume: '▶️' }
  const DESCS = {
    atag: 'A\'zolarni tag\'lash komandasi',
    stop: 'Jarayonni to\'xtatish komandasi',
    pause: 'Jarayonni to\'xtatib qo\'yish',
    resume: 'Jarayonni davom ettirish',
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>⌨️ Komandalar</h1>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          Guruhda ishlatadigan komandalaringizni o'zgartiring. O'zgarishlar bot komandalariga darhol tatbiq etiladi.
        </p>
      </div>

      {CMDS.map(cmd => (
        <div key={cmd} className="card" style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <span style={{ fontSize: 20 }}>{ICONS[cmd]}</span>
            <div>
              <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>{cmd}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{DESCS[cmd]}</div>
            </div>
          </div>
          <div className="cmd-row">
            <span className="cmd-label">/{cmds[cmd] || cmd}</span>
            <input
              className="input"
              value={edits[cmd] || ''}
              onChange={e => setEdits(v => ({ ...v, [cmd]: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && save(cmd)}
              placeholder={cmd}
              disabled={saving[cmd]}
            />
            <button
              className="reset-btn"
              onClick={() => reset(cmd)}
              disabled={saving[cmd]}
              title="Aslga qaytarish"
            >🔄</button>
          </div>
          <button
            className="btn btn-primary"
            style={{ padding: '10px 16px', fontSize: 13 }}
            onClick={() => save(cmd)}
            disabled={saving[cmd] || edits[cmd] === cmds[cmd]}
          >
            {saving[cmd] ? 'Saqlanmoqda...' : 'Saqlash'}
          </button>
        </div>
      ))}

      <Toast msg={toast.msg} type={toast.type} />
    </div>
  )
}
