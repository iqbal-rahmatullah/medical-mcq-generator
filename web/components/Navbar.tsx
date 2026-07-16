"use client"

import { usePathname } from "next/navigation"

import NavLink from "./NavLink"
import Avatar from "./Avatar"

export default function Navbar() {
  const pathname = usePathname()
  const navItems = [
    { label: "Knowledge", href: "/" },
    { label: "History", href: "/history" },
    { label: "Docs", href: "/docs" },
  ]

  return (
    <nav className='navbar'>
      <div className='navbar-inner'>
        <div className='brand'>
          <span className='logo-mark' aria-hidden='true'>
            <QuizIcon />
          </span>
          <p className='brand-title'>AQG</p>
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
            <Avatar name='User' />
          </div>
        </div>
      </div>
    </nav>
  )
}

function QuizIcon() {
  return (
    <svg viewBox='0 0 24 24' aria-hidden='true'>
      <path d='M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm1 4h8V5H8v2Zm0 4h3V9H8v2Zm5 0h3V9h-3v2Zm-5 4h3v-2H8v2Zm5 0h3v-2h-3v2Zm-5 4h8v-2H8v2Z' />
    </svg>
  )
}
