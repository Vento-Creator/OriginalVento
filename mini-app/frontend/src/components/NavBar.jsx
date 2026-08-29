import { NavLink } from 'react-router-dom'

const items = [
  { to: '/',            icon: '🏠', label: 'Bosh' },
  { to: '/subscription',icon: '⭐', label: 'Obuna' },
  { to: '/commands',    icon: '⌨️', label: 'Komandalar' },
  { to: '/stats',       icon: '📊', label: 'Statistika' },
  { to: '/profile',     icon: '👤', label: 'Profil' },
]

export default function NavBar({ user }) {
  const navItems = [...items]
  if (user?.is_admin) {
    navItems.splice(4, 0, { to: '/admin', icon: '🛠', label: 'Admin' })
  }

  return (
    <nav className="navbar">
      {navItems.map(({ to, icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
        >
          <span style={{ fontSize: 22 }}>{icon}</span>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
