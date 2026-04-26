import Link from "next/link"

export default function Footer() {
  return (
    <footer className='footer'>
      <div className='footer-inner'>
        <p className='footer-note'>(c) 2026 MedQGen</p>
        <Link className='footer-link' href='https://github.com/'>
          <span className='footer-link-icon' aria-hidden='true'>
            <svg viewBox='0 0 24 24'>
              <path d='M12 2C6.5 2 2 6.5 2 12c0 4.4 2.9 8.1 6.8 9.4.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.6 1 1.6 1 .9 1.5 2.4 1.1 3 .8.1-.7.4-1.1.7-1.4-2.2-.2-4.6-1.1-4.6-5 0-1.1.4-2.1 1-2.8-.1-.2-.4-1.3.1-2.6 0 0 .8-.3 2.7 1a9.4 9.4 0 0 1 4.9 0c1.9-1.3 2.7-1 2.7-1 .5 1.3.2 2.4.1 2.6.6.7 1 1.7 1 2.8 0 3.9-2.4 4.8-4.6 5 .4.3.7.9.7 1.8v2.7c0 .3.2.6.7.5A10 10 0 0 0 22 12c0-5.5-4.5-10-10-10Z' />
            </svg>
          </span>
          View on GitHub
        </Link>
      </div>
    </footer>
  )
}
