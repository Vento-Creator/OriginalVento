export default function LoadingScreen() {
  return (
    <div className="loading-screen">
      <div style={{
        width: 56, height: 56,
        background: 'linear-gradient(135deg,#6c63ff,#a855f7)',
        borderRadius: 16,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 28, marginBottom: 8,
        boxShadow: '0 8px 32px rgba(108,99,255,0.4)'
      }}>⚡</div>
      <div className="spinner" />
      <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>Yuklanmoqda...</p>
    </div>
  )
}
