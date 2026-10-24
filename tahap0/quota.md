# Kuota free tier Gemini (Tahap 0)

Isi dari AI Studio (Dashboard → Usage / Rate limits) untuk akun yang dipakai live. Model ID jangan di-hard-code di kode; salin ke `.env`.

- Tanggal cek:
- Tautan:

| Peran | Model ID | RPM | TPM | RPD | Catatan |
|---|---|---|---|---|---|
| blocker | | | | | |
| persona | | | | | |
| showrunner | | | | | |
| supervisor | | | | | |
| tts | | | | | |
| judge (offline) | | | | | |

## Kebutuhan mode B

Jalankan setelah tabel terisi (contoh):

```bash
python tahap0/quota_calc.py --minutes 20 60 --turn-audio-s 8 \
  --rpm-persona <RPM> --rpd-persona <RPD> --rpm-tts <RPM> --rpd-tts <RPD> ...
```

Tempel hasilnya di sini dan tulis kesimpulan: apakah 20 menit dan 60 menit muat, dan peran mana yang perlu model lain atau failover (§8).
