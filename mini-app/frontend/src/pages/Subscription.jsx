import { useEffect, useState } from 'react'
import { subscriptionApi } from '../api'

export default function Subscription({ user }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [paying, setPaying] = useState(false)

  useEffect(() => {
    subscriptionApi.get()
      .then(r => setData(r.data))
      .finally(() => setLoading(false))
  }, [])

  const openInvoice = () => {
    const tg = window.Telegram?.WebApp
    if (!tg) {
      alert("Telegram WebApp topilmadi. Stars to'lovi faqat Telegram messenjeri ichida ishlaydi.")
      return
    }

    setPaying(true)
    subscriptionApi.createInvoice()
      .then(res => {
        const link = res.data.invoice_link
        tg.openInvoice(link, (status) => {
          setPaying(false)
          if (status === 'paid' || status === 'completed') {
            tg.showAlert("Tabriklaymiz! To'lov muvaffaqiyatli amalga oshirildi.", () => {
              window.location.reload()
            })
          } else {
            tg.showAlert(`To'lov holati: ${status}`)
          }
        })
      })
      .catch(err => {
        setPaying(false)
        const errMsg = err.response?.data?.detail || err.message || "Xatolik yuz berdi"
        tg.showAlert(`To'lov oynasini ochib bo'lmadi:\n${errMsg}`)
      })
  }

  const expiryDate = data?.expiry_date
    ? new Date(data.expiry_date * 1000).toLocaleDateString('uz-UZ')
    : null

  const progressPct = data?.days_left
    ? Math.min(100, (data.days_left / 30) * 100)
    : 0

  return (
    <div className="page">
      <div className="page-header">
        <h1>⭐ Obuna</h1>
      </div>

      {/* Status card */}
      <div className="hero-card">
        <div style={{ fontSize: 40, marginBottom: 12 }}>
          {data?.is_active ? '✅' : '❌'}
        </div>
        <h2 style={{ fontSize: 20 }}>
          {data?.is_free
            ? 'Bepul (cheksiz)'
            : data?.is_active
              ? `${data.days_left} kun qoldi`
              : 'Obuna faol emas'
          }
        </h2>
        {expiryDate && (
          <p className="sub-text">Tugash sanasi: {expiryDate}</p>
        )}
        {data?.is_active && !data?.is_free && (
          <div className="sub-progress">
            <div className="sub-progress-bar" style={{ width: `${progressPct}%` }} />
          </div>
        )}
      </div>

      {/* Buy section */}
      {!data?.is_free && !loading && (
        <div className="card card-gradient">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <div style={{ fontSize: 32 }}>⭐</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>30 kunlik obuna</div>
              <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>100 Telegram Stars</div>
            </div>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
            Barcha funksiyalarga to'liq kirish: Utag, Taymer, Scraper va ko'proq.
          </p>
          <button className="btn btn-primary" onClick={openInvoice} disabled={paying}>
            {paying ? "Yuklanmoqda..." : "⭐ 100 Stars — Obuna olish"}
          </button>
        </div>
      )}

      {/* Payment history */}
      {data?.payment_history?.length > 0 && (
        <>
          <p className="section-title">To'lovlar tarixi</p>
          <div className="card">
            {data.payment_history.map((p, i) => (
              <div key={i} className="list-item">
                <div className="item-left">
                  <div className="item-icon">💳</div>
                  <div>
                    <div className="item-title">{p.amount} {p.currency}</div>
                    <div className="item-sub">
                      {new Date(p.created_at * 1000).toLocaleDateString('uz-UZ')}
                    </div>
                  </div>
                </div>
                <span className={`badge ${p.status === 'paid' ? 'badge-success' : 'badge-warning'}`}>
                  {p.status === 'paid' ? 'To\'langan' : p.status}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
