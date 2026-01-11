import NavLink from "./NavLink"
import IconButton from "./IconButton"
import Avatar from "./Avatar"

const navItems = [
  { label: "Generate", href: "#", active: true },
  { label: "History", href: "#", active: false },
  { label: "Docs", href: "#", active: false },
]

export default function Navbar() {
  return (
    <nav className='navbar'>
      <div className='navbar-inner'>
        <div className='brand'>
          <LogoMark />
          <div>
            <p className='brand-title'>MedQGen</p>
            <p className='brand-subtitle'>Medical MCQ Generator</p>
          </div>
        </div>

        <div className='nav-right'>
          <div className='nav-links'>
            {navItems.map((item) => (
              <NavLink
                key={item.label}
                href={item.href}
                label={item.label}
                active={item.active}
              />
            ))}
          </div>

          <div className='nav-actions'>
            <Avatar name='Dr. User' />
            <IconButton ariaLabel='Settings'>
              <GearIcon />
            </IconButton>
          </div>
        </div>
      </div>
    </nav>
  )
}

function LogoMark() {
  return (
    <div className='logo-mark' aria-hidden='true'>
      <svg viewBox='0 0 48 48' role='img'>
        <rect x='4' y='4' width='40' height='40' rx='12' />
        <path d='M24 12L36 24L24 36L12 24L24 12Z' />
      </svg>
    </div>
  )
}

function BellIcon() {
  return (
    <svg viewBox='0 0 24 24' aria-hidden='true'>
      <path d='M12 3a5 5 0 0 0-5 5v3.6c0 .9-.3 1.8-.9 2.5l-1.1 1.3h14l-1.1-1.3a3.6 3.6 0 0 1-.9-2.5V8a5 5 0 0 0-5-5Z' />
      <path d='M9.8 19a2.2 2.2 0 0 0 4.4 0' />
    </svg>
  )
}

function GearIcon() {
  return (
    <svg viewBox='0 0 24 24' aria-hidden='true'>
      <path d='M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Zm8 3.8-.9-.4.1-1.3-1.7-1-.9.9-1.2-.5-.4-1.2h-2l-.4 1.2-1.2.5-.9-.9-1.7 1 .1 1.3-.9.4v2l.9.4-.1 1.3 1.7 1 .9-.9 1.2.5.4 1.2h2l.4-1.2 1.2-.5.9.9 1.7-1-.1-1.3.9-.4v-2Z' />
    </svg>
  )
}
