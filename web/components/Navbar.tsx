"use client"

import { usePathname } from "next/navigation"

import NavLink from "./NavLink"
import IconButton from "./IconButton"
import Avatar from "./Avatar"

export default function Navbar() {
  const pathname = usePathname()
  const navItems = [
    { label: "Generate", href: "/" },
    { label: "History", href: "/history" },
    { label: "Docs", href: "/docs" },
  ]

  return (
    <nav className='navbar'>
      <div className='navbar-inner'>
        <div className='brand'>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src='/logo.png' alt='MedQGen' style={{ height: 48, width: 'auto' }} />
        </div>

        <div className='nav-right'>
          <div className='nav-links'>
            {navItems.map((item) => (
              <NavLink
                key={item.label}
                href={item.href}
                label={item.label}
                active={pathname === item.href}
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

function GearIcon() {
  return (
    <svg viewBox='0 0 24 24' aria-hidden='true'>
      <path d='M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Zm8 3.8-.9-.4.1-1.3-1.7-1-.9.9-1.2-.5-.4-1.2h-2l-.4 1.2-1.2.5-.9-.9-1.7 1 .1 1.3-.9.4v2l.9.4-.1 1.3 1.7 1 .9-.9 1.2.5.4 1.2h2l.4-1.2 1.2-.5.9.9 1.7-1-.1-1.3.9-.4v-2Z' />
    </svg>
  )
}
