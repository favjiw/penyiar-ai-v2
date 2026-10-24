import type { Blocker } from '../types'

interface Props {
  blocker: Blocker
  selected?: boolean
  busy?: boolean
  onSelect?: () => void
  onRegenerate?: () => void
}

/** Tampilan baca-saja satu varian blocker; dipakai di kartu varian dan blocker terkunci. */
export function BlockerView({ blocker }: { blocker: Blocker }) {
  return (
    <>
      <div className="section-label">Opening</div>
      <div className="hook">{blocker.opening.hook}</div>
      {blocker.opening.poin.length > 0 && <div className="angle">{blocker.opening.poin.join(' · ')}</div>}
      {blocker.topics.map((t, i) => (
        <div className="topic" key={t.id || i}>
          <div className="judul">
            {i + 1}. {t.judul}
          </div>
          <div className="angle">{t.sudut_pandang}</div>
          <ul>
            {t.poin.map((p, j) => (
              <li key={p.id || j}>
                {p.text}
                {p.perlu_cek && <span className="badge">perlu cek</span>}
              </li>
            ))}
          </ul>
          <div className="q">❓ {t.pertanyaan_penonton}</div>
          <div className="tr angle">↪ {t.transisi}</div>
        </div>
      ))}
      <div className="section-label">Closing</div>
      <div>
        {blocker.closing.rangkuman} <span className="angle">· {blocker.closing.ajakan}</span>
      </div>
    </>
  )
}

export function VariantCard({ blocker, selected, busy, onSelect, onRegenerate }: Props) {
  return (
    <article className={`card${selected ? ' selected' : ''}`}>
      <h3>{blocker.variant_label}</h3>
      <BlockerView blocker={blocker} />
      <div className="actions">
        <button className={selected ? '' : 'primary'} onClick={onSelect} disabled={busy || selected}>
          {selected ? 'Dipilih' : 'Pilih varian ini'}
        </button>
        <button onClick={onRegenerate} disabled={busy}>
          Buat ulang
        </button>
      </div>
    </article>
  )
}
