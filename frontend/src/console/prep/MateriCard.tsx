import type { Blocker } from '../../types'
import { Button, IconCheck, Pill } from '../../ui'

const PREVIEW_TOPICS = 3

interface Props {
  materi: Blocker
  selected: boolean
  /** Sudah tersimpan di server. Hasil generate baru belum: operator memilih yang disimpan. */
  saved: boolean
  busy?: boolean
  onUse: () => void
  onSave: () => void
  onEdit: () => void
  onRegenerate?: () => void
}

/** Satu pilihan materi (mockup Main, langkah 2): judul, kalimat pembuka, 3 topik pertama. */
export function MateriCard({ materi, selected, saved, busy, onUse, onSave, onEdit, onRegenerate }: Props) {
  const rest = materi.topics.length - PREVIEW_TOPICS
  return (
    <article className={`materi-card${selected ? ' is-selected' : ''}`} aria-current={selected ? 'true' : undefined}>
      <div className="materi-card__tags">
        {selected && (
          <Pill tone="blue">
            <IconCheck size={14} /> Dipakai
          </Pill>
        )}
        {materi.locked ? (
          <Pill>Pernah dipakai live</Pill>
        ) : saved ? (
          <Pill tone="success">Tersimpan</Pill>
        ) : (
          <Pill tone="yellow">Belum disimpan</Pill>
        )}
      </div>
      <h3 className="materi-card__title">{materi.variant_label}</h3>
      <p className="materi-card__hook">“{materi.opening.hook}”</p>
      <ol className="materi-card__topics">
        {materi.topics.slice(0, PREVIEW_TOPICS).map((t, i) => (
          <li key={i}>
            <span className="materi-card__n" aria-hidden="true">
              {i + 1}
            </span>
            {t.judul || <em>Topik tanpa judul</em>}
          </li>
        ))}
      </ol>
      {rest > 0 && <span className="materi-card__more">+{rest} topik lagi</span>}
      <div className="materi-card__actions">
        {!selected && (
          <Button variant="primary" onClick={onUse} disabled={busy}>
            {saved ? 'Pakai ini' : 'Simpan & pakai'}
          </Button>
        )}
        {!saved && (
          <Button onClick={onSave} disabled={busy}>
            Simpan
          </Button>
        )}
        <Button onClick={onEdit} disabled={busy}>
          Lihat &amp; ubah
        </Button>
        {onRegenerate && !saved && !materi.locked && (
          <Button variant="link" onClick={onRegenerate} disabled={busy}>
            {busy ? 'Membuat ulang…' : 'Buat ulang'}
          </Button>
        )}
      </div>
    </article>
  )
}
