import React, { useState } from 'react'

export default function LandingPage() {
  const [activeTab, setActiveTab] = useState('massdm')
  const tg = window.Telegram?.WebApp

  const features = {
    massdm: {
      icon: '📨',
      title: 'Mass DM (Aqlli Xabarnomalar)',
      subtitle: 'Spambot va cheklovlar bilan ishlash tizimi',
      details: [
        {
          title: '🤖 Spambot & Flood Himoyasi',
          text: 'Telegram tomonidan FloodWait (cheklov) yuzaga kelganda, tizim buni avtomatik aniqlaydi va jarayonni vaqtincha pauza qiladi. Belgingan muddatdan so\'ng yana o\'zi davom etadi.'
        },
        {
          title: '⚠️ Yuqori Xavf (High Risk) Nazorati',
          text: 'Tizim xabarlarni yuborishda hisobingiz xavf ostida ekanini aniqlasa, "Auto-Stop" mexanizmi ishga tushadi va jarayonni zudlik bilan to\'xtatadi.'
        },
        {
          title: '⏱️ Sozlanuvchan Kechikishlar',
          text: 'Har bir yuboriladigan xabar orasiga tasodifiy sekundlar (delay) yoki soatbay kechikishlar qo\'shib, akkauntingizning tabiiyligini saqlashingiz mumkin.'
        },
        {
          title: '📁 Moslashuvchan Kontent',
          text: 'Xabarlarni matn, rasm yoki formatlangan ko\'rinishda (HTML parse) yuborish imkoniyati.'
        }
      ]
    },
    utag: {
      icon: '🏷️',
      title: 'Utag & Taymer Tizimi',
      subtitle: 'Guruhlarda a\'zolarni tartibli tag qilish',
      details: [
        {
          title: '⌨️ Custom Komandalar',
          text: 'Default komandalar (/atag, /stop, /pause, /resume) o\'rniga o\'zingizga xos va maxfiy kalit so\'zlarni (masalan, .tayyor, .pauza) sozlang.'
        },
        {
          title: '🛑 Avtomatik Xavfsiz To\'xtash',
          text: 'Agar guruhda xabarlar ketma-ket o\'chishni boshlasa yoki bot huquqlari cheklansa (masalan, admin cheklovi), jarayon avtomatik tarzda to\'xtatiladi.'
        },
        {
          title: '⏱️ Aqlli Avto-Taymerlar',
          text: 'Guruh ichida har X daqiqada avtomatik o\'yinlar, xabarnomalar yoki ma\'lumotlar jo\'natib turuvchi taymerlarni masofadan sozlashingiz mumkin.'
        },
        {
          title: '✨ Multi-Xabarlar',
          text: 'Bitta guruhda bir vaqtning o\'zida bir nechta parallel taymer va taglash jarayonlarini ishga tushirish.'
        }
      ]
    },
    chat: {
      icon: '💬',
      title: 'Chat & Anonim Muloqot',
      subtitle: 'Bot ichidagi integratsiyalashgan chat tizimi',
      details: [
        {
          title: '👤 To\'g\'ridan-to\'g\'ri Muloqot',
          text: 'Bot foydalanuvchilari bir-birlari bilan bot ichida xuddi Telegram chat kabi oson, xavfsiz va tezkor suhbatlasha oladilar.'
        },
        {
          title: '🤫 Anonimlik Rejimi',
          text: 'Xabarlarni to\'liq anonim ko\'rinishda boshqa foydalanuvchilarga yoki guruhga yuborish imkoniyati (/say anon).'
        },
        {
          title: '🚫 Block & Mute Tizimi',
          text: 'Sizga halal berayotgan foydalanuvchilarni block qilish yoki bildirishnomalarni vaqtincha mute (ovozsiz) qilib qo\'yish imkoniyatlari.'
        },
        {
          title: '📩 Admin Bilan Aloqa',
          text: 'Adminlar bilan to\'g\'ridan-to\'g\'ri bog\'lanish, shikoyat va takliflarni fayl/rasm ko\'rinishida yuborish.'
        }
      ]
    },
    others: {
      icon: '⚡',
      title: 'Boshqa Imkoniyatlar',
      subtitle: 'Qo\'shimcha asboblar va boshqaruv',
      details: [
        {
          title: '🔍 Guruhlar Scraperi',
          text: 'Ochiq guruhlardagi barcha a\'zolarni (hatto yashirin bo\'lsa ham) skraping qilish va ularni kategoriyalangan bazalarga ajratish.'
        },
        {
          title: '📣 Yangiliklar & E\'lonlar',
          text: 'Botga kiritiladigan eng so\'nggi o\'zgarishlar, yangilanishlar logi va yangiliklar bo\'limi orqali doimiy xabardor bo\'lib turish.'
        },
        {
          title: '💳 Stars To\'lovlari',
          text: 'Telegram Stars tizimi orqali 100% xavfsiz va bir soniyada faollashadigan premium obuna tizimi.'
        },
        {
          title: '🛠️ Premium Admin Panel',
          text: 'Jami foydalanuvchilar, ularning obuna muddati, to\'lovlar tarixi va tizim statistikasini real-vaqtda boshqarish paneli.'
        }
      ]
    }
  }

  return (
    <div className="page" style={{ padding: '30px 16px 50px', maxWidth: '800px', margin: '0 auto', width: '100%' }}>
      {/* Header / Brand */}
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <div style={{
          width: 64, height: 64,
          background: 'linear-gradient(135deg, #6c63ff, #a855f7)',
          borderRadius: 20,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 32, margin: '0 auto 16px',
          boxShadow: '0 8px 32px rgba(108,99,255,0.3)'
        }}>⚡</div>
        <h1 style={{ fontSize: 26, fontWeight: 800, background: 'linear-gradient(135deg, #6c63ff, #a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', letterSpacing: '-0.5px' }}>
          Vento Assistant
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6, lineHeight: '1.4' }}>
          Telegram guruhlar, a'zolar va xabarnomalar bilan ishlash uchun professional yechimlar.
        </p>
      </div>

      {/* Navigation Tabs */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 6,
        background: 'var(--card-bg)',
        border: '1px solid var(--card-border)',
        padding: 4,
        borderRadius: 12,
        marginBottom: 20,
        maxWidth: '500px',
        width: '100%',
        margin: '0 auto 20px'
      }}>
        {Object.keys(features).map(key => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: '10px 0',
              borderRadius: 8,
              border: 'none',
              background: activeTab === key ? 'linear-gradient(135deg, #6c63ff, #a855f7)' : 'transparent',
              color: activeTab === key ? '#fff' : 'var(--text-muted)',
              fontWeight: 600,
              fontSize: 12,
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 4,
              transition: 'all 0.2s'
            }}
          >
            <span style={{ fontSize: 18 }}>{features[key].icon}</span>
            <span style={{ fontSize: 10 }}>
              {key === 'massdm' ? 'Mass DM' : key === 'utag' ? 'Utag' : key === 'chat' ? 'Chat' : 'Boshqa'}
            </span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ animation: 'fadeIn 0.3s ease' }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>
          {features[activeTab].title}
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          {features[activeTab].subtitle}
        </p>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '16px',
          marginBottom: '30px'
        }}>
          {features[activeTab].details.map((detail, idx) => (
            <div key={idx} className="card" style={{ padding: '16px', margin: 0, background: 'rgba(255,255,255,0.03)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%' }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: '#fff', marginBottom: 6 }}>
                {detail.title}
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: '1.5' }}>
                {detail.text}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Bot Link */}
      <div className="card card-gradient" style={{ textAlign: 'center', padding: '24px', maxWidth: '500px', margin: '0 auto' }}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Vento Assistant'ni Boshlang</h3>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 18, lineHeight: '1.4' }}>
          Tizimdan foydalanish uchun Telegram botimizga kiring va boshqaruv buyruqlarini bering.
        </p>
        <a 
          href={`https://t.me/${import.meta.env.VITE_BOT_USERNAME || 'empire_family_bot'}`}
          className="btn btn-primary"
          style={{ textDecoration: 'none' }}
        >
          🤖 Botni Telegramda ochish
        </a>
      </div>
    </div>
  )
}
