import type { Blocker, BlockerTopic } from '../types'

interface Props {
  blocker: Blocker
  onChange: (b: Blocker) => void
}

const MAX_TOPICS = 3

function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length) return list
  const copy = [...list]
  const [item] = copy.splice(from, 1)
  copy.splice(to, 0, item)
  return copy
}

const emptyTopic = (): BlockerTopic => ({
  id: '',
  judul: 'Topik baru',
  sudut_pandang: '',
  poin: [{ id: '', text: '', perlu_cek: false }],
  pertanyaan_penonton: '',
  transisi: '',
})

/** Editor inline draf blocker (FR-1): ubah teks, tambah/hapus/geser poin dan topik. */
export function BlockerEditor({ blocker: b, onChange }: Props) {
  const set = (patch: Partial<Blocker>) => onChange({ ...b, ...patch })
  const setTopic = (i: number, patch: Partial<BlockerTopic>) =>
    set({ topics: b.topics.map((t, k) => (k === i ? { ...t, ...patch } : t)) })

  return (
    <div>
      <label className="field">
        Label varian
        <input type="text" value={b.variant_label} onChange={(e) => set({ variant_label: e.target.value })} />
      </label>

      <fieldset>
        <legend>Opening</legend>
        <label className="field">
          Hook
          <input type="text" value={b.opening.hook} onChange={(e) => set({ opening: { ...b.opening, hook: e.target.value } })} />
        </label>
        {b.opening.poin.map((p, j) => (
          <div className="row" key={j}>
            <input
              type="text"
              value={p}
              aria-label={`Poin opening ${j + 1}`}
              onChange={(e) => set({ opening: { ...b.opening, poin: b.opening.poin.map((x, k) => (k === j ? e.target.value : x)) } })}
            />
            <button className="icon" title="Hapus poin" onClick={() => set({ opening: { ...b.opening, poin: b.opening.poin.filter((_, k) => k !== j) } })}>
              ✕
            </button>
          </div>
        ))}
        <div className="row">
          <button className="small" onClick={() => set({ opening: { ...b.opening, poin: [...b.opening.poin, ''] } })}>
            + Poin opening
          </button>
        </div>
      </fieldset>

      {b.topics.map((t, i) => (
        <fieldset key={i}>
          <legend>Topik {i + 1}</legend>
          <div className="row">
            <input type="text" value={t.judul} aria-label="Judul topik" onChange={(e) => setTopic(i, { judul: e.target.value })} />
            <span className="topic-tools">
              <button className="icon" title="Geser ke atas" disabled={i === 0} onClick={() => set({ topics: move(b.topics, i, i - 1) })}>
                ↑
              </button>
              <button className="icon" title="Geser ke bawah" disabled={i === b.topics.length - 1} onClick={() => set({ topics: move(b.topics, i, i + 1) })}>
                ↓
              </button>
              <button className="icon" title="Hapus topik" disabled={b.topics.length === 1} onClick={() => set({ topics: b.topics.filter((_, k) => k !== i) })}>
                Hapus topik
              </button>
            </span>
          </div>
          <label className="field" style={{ marginTop: 8 }}>
            Sudut pandang
            <input type="text" value={t.sudut_pandang} onChange={(e) => setTopic(i, { sudut_pandang: e.target.value })} />
          </label>
          <div className="section-label">Poin obrolan</div>
          {t.poin.map((p, j) => (
            <div className="row" key={j}>
              <input
                type="text"
                value={p.text}
                aria-label={`Poin ${j + 1}`}
                onChange={(e) => setTopic(i, { poin: t.poin.map((x, k) => (k === j ? { ...x, text: e.target.value } : x)) })}
              />
              <label className="chk" title="Tandai klaim yang perlu dicek operator">
                <input
                  type="checkbox"
                  checked={p.perlu_cek}
                  onChange={(e) => setTopic(i, { poin: t.poin.map((x, k) => (k === j ? { ...x, perlu_cek: e.target.checked } : x)) })}
                />
                perlu cek
              </label>
              <button className="icon" title="Naik" disabled={j === 0} onClick={() => setTopic(i, { poin: move(t.poin, j, j - 1) })}>
                ↑
              </button>
              <button className="icon" title="Turun" disabled={j === t.poin.length - 1} onClick={() => setTopic(i, { poin: move(t.poin, j, j + 1) })}>
                ↓
              </button>
              <button className="icon" title="Hapus poin" disabled={t.poin.length === 1} onClick={() => setTopic(i, { poin: t.poin.filter((_, k) => k !== j) })}>
                ✕
              </button>
            </div>
          ))}
          <div className="row">
            <button className="small" onClick={() => setTopic(i, { poin: [...t.poin, { id: '', text: '', perlu_cek: false }] })}>
              + Poin
            </button>
          </div>
          <div className="grid2" style={{ marginTop: 8 }}>
            <label className="field">
              Pertanyaan ke penonton
              <input type="text" value={t.pertanyaan_penonton} onChange={(e) => setTopic(i, { pertanyaan_penonton: e.target.value })} />
            </label>
            <label className="field">
              Kalimat transisi
              <input type="text" value={t.transisi} onChange={(e) => setTopic(i, { transisi: e.target.value })} />
            </label>
          </div>
        </fieldset>
      ))}
      {b.topics.length < MAX_TOPICS && (
        <div className="row">
          <button className="small" onClick={() => set({ topics: [...b.topics, emptyTopic()] })}>
            + Topik
          </button>
        </div>
      )}

      <fieldset>
        <legend>Closing</legend>
        <div className="grid2">
          <label className="field">
            Rangkuman
            <input type="text" value={b.closing.rangkuman} onChange={(e) => set({ closing: { ...b.closing, rangkuman: e.target.value } })} />
          </label>
          <label className="field">
            Ajakan
            <input type="text" value={b.closing.ajakan} onChange={(e) => set({ closing: { ...b.closing, ajakan: e.target.value } })} />
          </label>
        </div>
      </fieldset>
    </div>
  )
}
