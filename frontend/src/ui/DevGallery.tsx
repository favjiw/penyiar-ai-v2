/** Galeri komponen dasar, hanya di mode dev (`/_ui`), untuk cek visual dan kontras. Tidak ikut build produksi. */
import { useState } from 'react'
import { Alert, Button, Card, LevelBars, LiveBadge, Pill, Ring, useAudioLevel } from '.'
import { IconArrowRight, IconMicOff, IconMonitorOff, IconPlay } from './icons'

export function DevGallery() {
  const [level, setLevel] = useState(0)
  const [mic, setMic] = useState<MediaStream | null>(null)
  const micLevel = useAudioLevel(mic)
  const [remaining, setRemaining] = useState(95)
  const [showYellow, setShowYellow] = useState(true)
  const [showBlue, setShowBlue] = useState(true)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-console)', padding: 32, display: 'grid', gap: 24, fontFamily: 'var(--font)' }}>
      <h1 style={{ margin: 0, fontSize: 28 }}>Komponen dasar</h1>

      <Card title="Tombol">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <Button variant="primary" size="lg">Buat materi</Button>
          <Button variant="primary" icon={<IconPlay size={18} />}>Mulai live</Button>
          <Button>Jeda</Button>
          <Button>Topik selanjutnya</Button>
          <Button variant="ink">Pilih mikrofon lain</Button>
          <Button variant="danger">Akhiri siaran</Button>
          <Button variant="link" icon={<IconArrowRight size={18} />}>Lihat &amp; ubah</Button>
          <Button disabled>Nonaktif</Button>
          <Button variant="primary" size="xl">Siap live</Button>
        </div>
      </Card>

      <Card title="Pil dan badge">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <LiveBadge />
          <LiveBadge paused />
          <Pill>Opening</Pill>
          <Pill tone="blue">Tanya penonton</Pill>
          <Pill tone="yellow">Giliranmu</Pill>
          <Pill tone="orange">Lewat waktu</Pill>
          <Pill tone="success">Siap</Pill>
          <Pill tone="danger">Terputus</Pill>
        </div>
      </Card>

      <Card title="Cincin waktu">
        <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'center' }}>
          <Ring remainingS={312} limitS={540} />
          <Ring remainingS={22} limitS={540} />
          <Ring remainingS={-134} limitS={540} />
          <Ring remainingS={-3599} limitS={540} />
          <Ring remainingS={remaining} limitS={120} size={160} />
          <label style={{ display: 'grid', gap: 4 }}>
            Sisa (dtk): {remaining}
            <input type="range" min={-200} max={120} value={remaining} onChange={(e) => setRemaining(Number(e.target.value))} />
          </label>
        </div>
      </Card>

      <Card title="Bar level suara">
        <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'center' }}>
          <LevelBars level={0} />
          <LevelBars level={0.5} />
          <LevelBars level={1} />
          <LevelBars level={level} bars={4} height={40} />
          <input type="range" min={0} max={1} step={0.05} value={level} onChange={(e) => setLevel(Number(e.target.value))} aria-label="Level simulasi" />
          <span style={{ display: 'inline-flex', gap: 12, alignItems: 'center' }}>
            <LevelBars level={micLevel} />
            <Button
              onClick={async () => {
                if (mic) {
                  mic.getTracks().forEach((t) => t.stop())
                  setMic(null)
                } else setMic(await navigator.mediaDevices.getUserMedia({ audio: true }))
              }}
            >
              {mic ? 'Matikan mic' : 'Tes mic'}
            </Button>
          </span>
        </div>
      </Card>

      <Card title="Peringatan">
        <div className="ui-alert-stack">
          <Alert
            level="red"
            icon={<IconMicOff />}
            title="Mikrofon studio tidak terdengar"
            message="Sudah 8 detik tidak ada suara dari mixer. Penyiar belum bisa ngobrol dengan AI."
            time="15.27"
            actions={
              <>
                <Button variant="ink">Pilih mikrofon lain</Button>
                <Button>Jeda siaran</Button>
              </>
            }
          />
          <Alert
            level="red"
            icon={<IconMonitorOff />}
            title="Layar untuk OBS tertutup"
            message="Penonton tidak mendengar suara AI. Buka lagi lalu pastikan OBS menangkap jendela yang sama."
            time="15.26"
            actions={<Button variant="ink">Buka lagi layar OBS</Button>}
          />
          {showYellow && (
            <Alert
              level="yellow"
              title="Kuota suara AI hampir habis"
              message="Setelah habis, suara pindah ke cadangan dan terdengar sedikit berbeda."
              time="15.25"
              onDismiss={() => setShowYellow(false)}
              actions={<Button variant="ink">Lanjut ke penutup</Button>}
            />
          )}
          {showBlue && <Alert level="blue" title="Suara cadangan aktif. Siaran tetap jalan." time="15.24" onDismiss={() => setShowBlue(false)} />}
          <Button onClick={() => (setShowYellow(true), setShowBlue(true))}>Tampilkan lagi</Button>
        </div>
      </Card>
    </div>
  )
}
