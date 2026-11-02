import { Home, Users, ArrowLeftRight, Workflow, BarChart3, BookOpen, Bot, Zap } from 'lucide-react'
import { NavLink } from 'react-router-dom'

// lucide-react dropped brand icons (no `Github` export as of v1.x), so use the official mark inline.
function GithubIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 .5C5.37.5 0 5.87 0 12.5c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.21.09 1.84 1.24 1.84 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.13-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.66.25 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.49 5.93.43.37.81 1.1.81 2.22v3.29c0 .32.21.7.82.58A12.01 12.01 0 0 0 24 12.5C24 5.87 18.63.5 12 .5z" />
    </svg>
  )
}

const links: { to: string; label: string; Icon: typeof Home; end?: boolean }[] = [
  { to: '/', label: 'Home', Icon: Home, end: true },
  { to: '/customers', label: 'Customers', Icon: Users },
  { to: '/transactions', label: 'Transactions', Icon: ArrowLeftRight },
  { to: '/data-products', label: 'Data Products', Icon: Workflow },
  { to: '/analytics', label: 'Analytics', Icon: BarChart3 },
  { to: '/cep', label: 'CEP Patterns', Icon: Zap },
  { to: '/chat', label: 'Assistant', Icon: Bot },
]

export default function Sidebar() {
  return (
    <div className="sidebar-container">
      <nav className="sidebar">
        {links.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `sidebar__link${isActive ? ' sidebar__link--active' : ''}`}
          >
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar__footer">
        <a
          href="https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/docs/demo_script.md"
          target="_blank"
          rel="noopener noreferrer"
          className="sidebar__link sidebar__link--footer"
        >
          <BookOpen size={18} />
          <span>Demonstration Script</span>
        </a>
       
        <a
          href="https://github.com/jbcodeforce/streamhouse_c360_demo"
          target="_blank"
          rel="noopener noreferrer"
          className="sidebar__link sidebar__link--footer"
        >
          <GithubIcon size={18} />
          <span>GitHub Repo</span>
        </a>
      </div>
    </div>
  )
}

