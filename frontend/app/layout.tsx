import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'ExchangeTreasurer — Your money, made clear',
  description: 'A financial copilot for international students navigating their first year in the US.',
  generator: 'v0.app',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  // The app itself is light-only; these are the browser chrome around it, and
  // they take the same paper and navy as the stylesheet's --paper and --vault.
  colorScheme: 'light',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#eef1f5' },
    { media: '(prefers-color-scheme: dark)', color: '#10202f' },
  ],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
        {/* Only on Vercel: its script is served by the platform, so anywhere
            else (the demo laptop, a production build run locally) it 404s and
            puts a red line in the console mid-demo. */}
        {process.env.VERCEL === '1' && <Analytics />}
      </body>
    </html>
  )
}
