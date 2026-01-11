import type { Metadata } from "next"
import { Manrope, Sora } from "next/font/google"
import type { ReactNode } from "react"

import "./globals.css"

export const metadata: Metadata = {
  title: "AQG Medical",
  description: "Generate medical questions easily with AQG Medical.",
}

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  display: "swap",
})

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-sora",
  display: "swap",
})

type RootLayoutProps = {
  children: ReactNode
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang='id'>
      <body className={`${manrope.variable} ${sora.variable}`}>{children}</body>
    </html>
  )
}
