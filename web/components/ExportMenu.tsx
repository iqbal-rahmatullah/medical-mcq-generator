"use client"

import { useEffect, useRef, useState } from "react"

type ExportFormat = "json" | "pdf" | "docx"

type ExportMenuProps = {
  idPrefix: string
  onExport: (format: ExportFormat) => void
}

const EXPORT_OPTIONS: { format: ExportFormat; icon: string; title: string; desc: string }[] = [
  { format: "json", icon: "", title: "JSON", desc: "Raw data" },
  { format: "pdf", icon: "📕", title: "PDF", desc: "Print-ready exam" },
  { format: "docx", icon: "📘", title: "DOCX", desc: "Editable document" },
]

export default function ExportMenu({ idPrefix, onExport }: ExportMenuProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  const handleExport = (format: ExportFormat) => {
    setOpen(false)
    onExport(format)
  }

  return (
    <div className='export-dropdown' ref={ref}>
      <button
        id={`${idPrefix}-export-btn`}
        type='button'
        className='export-trigger'
        onClick={() => setOpen((o) => !o)}
        aria-haspopup='true'
        aria-expanded={open}
      >
        <span>⬇</span> Export
      </button>
      {open ? (
        <div className='export-menu' role='menu'>
          {EXPORT_OPTIONS.map((opt) => (
            <button
              key={opt.format}
              id={`${idPrefix}-export-${opt.format}-btn`}
              type='button'
              className='export-menu-item'
              role='menuitem'
              onClick={() => handleExport(opt.format)}
            >
              <span className='export-icon'>{opt.icon}</span>
              <span>
                <strong>{opt.title}</strong>
                <small>{opt.desc}</small>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
