import { useEffect } from 'react'

/** Rute tak dikenal → 404, bukan konsol (HANDOFF §2), supaya salah ketik /stage tidak membuka konsol kedua. */
export function NotFound() {
  useEffect(() => {
    document.title = 'Halaman tidak ada · Penyiar AI HITS'
  }, [])
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg-console)', fontFamily: 'var(--font)', padding: 24 }}>
      <div className="ui-card" style={{ maxWidth: 480, textAlign: 'center' }}>
        <h1 style={{ fontSize: 28, margin: '0 0 8px' }}>Halaman tidak ada</h1>
        <p style={{ margin: '0 0 20px', color: 'var(--n-600)' }}>
          Alamat <code>{window.location.pathname}</code> tidak dikenal.
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
          <a className="ui-btn ui-btn--primary" href="/">
            Buka konsol
          </a>
          <a className="ui-btn" href="/prompter">
            Buka prompter
          </a>
        </div>
      </div>
    </main>
  )
}
