# Uji endpoint kompatibel OpenAI: cosmoshub (24 Okt 2026)

Endpoint `https://api.cosmoshub.tech/v1` (key dari Favian, hanya lewat env var). 45 model; satu Gemini: `gemini-3.8-flash`. Dipakai lewat model `compat:gemini-3.8-flash` (lihat `.env.example`).

## Temuan

| Hal | Hasil |
|---|---|
| Format | `/chat/completions` gaya OpenAI; `response_format: json_schema` didukung; `json_object` kadang dibungkus ```` ```json ```` (sudah ditangani) |
| Reasoning | Default memakai ±500–700 token reasoning → 8–18 s per giliran persona. `reasoning_effort: "none"` → ±3 s tanpa token reasoning |
| Biaya | **Berbayar**: `usage.cost` ±$0,00001 per panggilan tanpa reasoning (±$0,00003 dengan reasoning). Satu sesi 20 menit (±240 panggilan) ≈ $0,003 |
| Kuota | Tidak ada header batas; tidak kena 429 selama uji |
| Supervisor (5 kasus tangan) | 5/5 benar, 2,4–11,8 s |

## Sesi mode B 6,9 menit (semua peran lewat compat, TTS mock)

Log `show_20261024_161824_8b7f`: 34 giliran, `completed`, 0 galat HTTP.

| Metrik | Gemini langsung (gerbang sesi 3) | compat `gemini-3.8-flash` |
|---|---|---|
| Persona p50 | 1,4 s | 3,7 s (4 timeout >10 s) |
| Supervisor p50 | 1,2 s | 3,7 s (10/34 timeout di 5 s) |
| Jeda p50 / p95 | 0 / 8,5 s | 2,8 s / 12,4 s |

Isi obrolan baik dan persona konsisten.

## Rekomendasi [C]

- Bukan model utama live: jeda p50 sudah di atas target ≤1,5 s (FR-2).
- Cocok sebagai **cadangan saat kuota harian Gemini habis** (`GEMINI_MODEL_PERSONA_FALLBACK=compat:gemini-3.8-flash`) dan untuk **eksperimen offline FR-14** (tidak dibatasi 500 RPD; latensi tidak penting).
- Karena berbayar, pemakaiannya bertentangan dengan aturan Rp0 (PRD §1.3, §8) kecuali diputuskan Favian.
