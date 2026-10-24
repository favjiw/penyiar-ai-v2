# Analisis Rekaman Live TikTok HITS Unikom Radio — 20 Oktober 2026

Rekaman: `Record_2026-10-20-10-08-44_….mp4` (dimulai 10.08 WIB, 1080×2340, 60 fps, 2,2 GB).
Bahan analisis: transkrip Whisper medium untuk seluruh audio, 260 frame (satu frame per 10 detik), dan log komentar yang dibaca dari frame.
Tujuan: mendokumentasikan kondisi saat ini (*as-is*) program yang akan diubah menjadi penyiar AI, sebagai acuan untuk sistem dan skripsi (kealamian percakapan, penanganan komentar, struktur sesi).

> Konteks: rekaman ini adalah **program Live Streaming TikTok HITS UNIKOM yang sedang berjalan saat ini**, dibawakan penyiar manusia (dalam sesi ini bersama bintang tamu; stiker LOKALAND terlihat di layar). **Program inilah yang akan diubah menjadi penyiar AI.** Jadi temuan di bawah adalah gambaran proses *as-is* yang harus digantikan atau ditingkatkan oleh sistem *to-be*.

## 1. Ringkasan cepat

- **Durasi efektif 32 menit 19 detik.** Setelah itu audio senyap dan gambar membeku sampai akhir file (10 menit 53 detik). Kemungkinan siaran terputus di sisi perekam, sehingga bagian penutup sesi tidak terekam.
- Hanya sekitar **15 menit yang on air**. Sisanya adalah pra-siaran (3,4 menit) dan jeda radio (sekitar 13,5 menit).
- **Selama jeda radio, penonton TikTok tidak mendengar lagu atau iklan.** Mereka mendengar obrolan santai penyiar dengan tamu dari mikrofon ruangan.
- **Tidak satu pun dari 4 request lagu penonton dijawab saat on air.** Komentar hanya direspons di pra-siaran (2 komentar).
- Penonton serentak 2 sampai 9 orang. Jumlah like naik dari 518 menjadi 1,3 ribu.

## 2. Linimasa sesi

| Waktu rekaman | Bagian | Isi |
| --- | --- | --- |
| 00:00–03:20 | Pra-siaran | Kamera sudah live. Penyiar menanggapi komentar ("udah bisa request? boleh dong"). Tamu datang sekitar 01:20 dan berbasa-basi (perjalanan, hotel, yoga). |
| 03:22–03:35 | Teaser | "Sobat Hits, sekarang udah kedatangan bintang tamu lho… siapa ya kira-kira?" |
| 03:36 | Station ID | "103.9 Hits Unikom Radio, semua hits ada di sini" |
| 03:41–11:04 | On air 1: wawancara | Perkenalan tamu (musisi dari Malaysia, ditranskrip sebagai "Dada Alatas"; ejaan belum diverifikasi). Topik: asal mula menulis lagu, label, alasan ke Indonesia, lagu "Yang Ada" yang dirilis sehari sebelum ulang tahunnya. |
| 11:04–11:26 | Penutup segmen dan CTA | "Udah kepo belum? Kalau kepo tungguin." Ajakan bertanya lewat komentar TikTok atau WhatsApp. |
| ±11:30–25:00 | Off air (iklan dan lagu di radio) | Obrolan santai: KL, kuliner Bandung, rawon, bahasa Ambon ("beta"), rendang Malaysia. Di 16:08: "Ini kita ada iklan dulu… udah ini satu lagu baru kita masuk lagi". Di 22:07 penyiar menjelaskan sisa rundown kepada tamu: lagu, ngobrol, break lagu, lalu akapela. |
| 25:01 | Kembali on air | "Kita on air lagi ya" (Whisper: "kita kan air lagi ya"). Rekap: "'Yang Ada' dari Dada udah di-play di Hits Unikom Radio." |
| 25:07–32:19 | On air 2: wawancara lanjutan | Makna lagu (bersyukur), cerita proses, zodiak Virgo dan perfeksionis, genre, harapan. Ditutup dengan pesan untuk pendengar: "jangan lupa dengerin… kalau gengsi bilang terima kasih, kasih aja lagu ini". |
| 32:19–43:12 | Rusak | Tidak ada audio dan gambar beku. Akapela dan closing tidak terekam. |

Batas off air disimpulkan dari ucapan penyiar di 16:08 dan 25:01 ("kita on air lagi", tafsiran dari hasil Whisper "kita kan air lagi") serta dari level audio. Level audio on air sekitar −15 sampai −20 dB, sedangkan pra-siaran dan off air sekitar −21 sampai −27 dB. Ketelitian batasnya kira-kira ±30 detik.

## 3. Temuan

### 3.1 Live TikTok bukan relay siaran radio
TikTok mengambil suara ruangan dari ponsel di studio, bukan feed program radio. Akibatnya, selama sekitar 13,5 menit jeda radio (42% dari konten efektif), penonton TikTok mendengar obrolan tanpa naskah. Lagu tamu yang diputar di radio tidak terdengar di TikTok. Sebaliknya, obrolan off air inilah bagian yang paling cair dan paling banyak bercanda.

**Implikasi untuk sistem:** rundown 1 jam di `keputusan-desain-sistem.md` mengasumsikan slot lagu benar-benar diputar di live. Ada tiga pilihan desain yang perlu ditanyakan ke HITS:
- (a) lagu diputar di TikTok, dengan memperhitungkan risiko hak cipta dan mute dari TikTok;
- (b) slot lagu diganti obrolan santai ber-register off air, seperti yang terjadi di rekaman ini;
- (c) slot lagu diisi visual atau teks "Now playing".

Rekaman ini menunjukkan bahwa praktik HITS saat ini mendekati pilihan (b), walaupun tidak direncanakan. Karena program inilah yang akan diganti, perilaku saat jeda ini termasuk kebutuhan yang harus ditiru atau diputuskan ulang secara eksplisit di sistem AI.

### 3.2 Penanganan komentar: permintaan utama adalah request lagu
Dari 19 entri di log komentar, ada 4 request lagu dari penonton (Theda Januar, singlehits, LetishaAldeeva, Starisa), yang muncul setelah pancingan dari akun host "MAU DI PLAY HITS INDONESIA APA SOB?". Komentar lainnya berupa sapaan atau pujian ("aduhh meni gareulisss"), komentar di luar topik (empat komentar tentang Barcelona dari satu akun), dan "lah tamu".
- Saat on air, penyiar fokus ke tamu dan **tidak membacakan komentar**, padahal CTA di 11:10 mengajak penonton bertanya.
- Komentar baru direspons di pra-siaran, ketika belum ada tamu.

**Implikasi:**
- Fitur "baca komentar" di sistem AI memperbaiki celah yang nyata, karena penonton bertanya tetapi tidak dijawab.
- Jenis komentar yang dominan adalah **request lagu**. Komentar ini sebaiknya diarahkan ke modul musik (antrean request), bukan hanya dijadikan topik obrolan.
- Komentar di luar topik seperti soal Barcelona memerlukan kebijakan: diabaikan, atau dijembatani singkat ke Tema.

### 3.3 Pola percakapan penyiar (bahan prompt dan pembanding kealamian)
Pola yang terlihat dalam segmen on air:
- **Kalimat pembuka segmen dengan teaser:** "siapa ya kira-kira? daripada penasaran, yuk…"
- **Sapaan kepada audiens disisipkan di tengah obrolan:** "Sobat Hits" muncul 7 kali saat on air.
- **Reformulasi jawaban tamu:** "jatuhnya jadi hobi yang dibayar", "berarti darah Jawa gitu ya".
- **Sahutan pendek:** "oh oke", "iya bener", "wow", "ciee", "aduh".
- **Merujuk tamu sebagai orang ketiga untuk audiens:** "seorang Dada ini…"
- **Penutup segmen yang menggantung:** "kalau kepo tungguin".
- **Rekap setelah lagu:** "'Yang Ada' udah di-play…"
- **Penutup yang ditarik menjadi pesan untuk pendengar:** "Sobat Hits yang lagi terpuruk… jangan lupa dengerin…"

Statistik kasar dari segmen Whisper (indikatif, karena bukan giliran bicara yang sebenarnya):

| Bagian | Kata/menit | Segmen ≤3 kata |
| --- | --- | --- |
| Pra-siaran | 77 | 50% |
| On air 1 | 138 | 22% |
| Off air | 118 | 34% |
| On air 2 | 139 | 16% |

Saat on air, penyiar dan tamu bicara lebih padat dan lebih jarang menyela. Saat off air, ada lebih banyak sahutan pendek dan pertanyaan balik.

**Implikasi:**
- Pola di atas bisa dipakai sebagai contoh *few-shot* untuk register on air.
- Untuk kealamian, rekaman ini menambah pembanding kedua selain transcript on-air 50:45 yang sudah ada, dengan dua register (on air dan off air).
- Namun formatnya **wawancara tamu yang asimetris** (pewawancara dan narasumber), berbeda dari dua co-host setara. Jangan dipakai sebagai satu-satunya acuan untuk percakapan AI vs AI.

### 3.4 Catatan untuk Supervisor dan identity drift
Tamu secara sadar menyesuaikan gaya bahasanya dengan lawan bicara: "di Indonesia otomatis 'beta'", campuran Melayu, Indonesia, dan Ambon, serta *code-switching* ke bahasa Inggris. Penyiar ikut bermain dengan pilihan kata itu ("beta, karena bukan alpha").

Bagi manusia, konvergensi gaya ringan seperti ini wajar dan malah membuat percakapan terasa alami. Jika Supervisor terlalu ketat memperlakukan setiap perubahan gaya sebagai drift, kealamian bisa turun.

**Saran:** di definisi operasional skripsi, bedakan *drift identitas* (nilai, latar, dan peran persona berubah) dari *akomodasi gaya* (pilihan kata menyesuaikan lawan bicara). Ini bisa menjadi argumen yang baik ketika menghadapi reviewer.

### 3.5 Unsur rundown yang terlihat
Unsur yang terlihat di rekaman: teaser, station ID ("semua hits ada di sini"), pembukaan segmen, CTA (komentar TikTok dan WhatsApp), iklan, lagu, rekap setelah lagu, dan rencana akapela di akhir. Ini konsisten dengan pola format clock: Talk, lagu, dan spot.

Ada satu jenis Talk yang **belum ada** di tiga jenis segmen yang sudah didokumentasikan, yaitu **wawancara bintang tamu**. Karena rekaman ini adalah program yang akan diganti, perlu diputuskan bersama HITS: apakah versi AI hanya menggantikan sesi tanpa tamu (saat penyiar tidak bisa hadir), atau salah satu penyiar AI juga harus bisa mewawancarai tamu manusia. Pilihan kedua berada di luar desain AI vs AI saat ini dan sebaiknya dicatat sebagai batasan.

## 4. Rekomendasi tindak lanjut
1. Tanyakan ke HITS apa yang semestinya terdengar di TikTok saat lagu atau iklan radio diputar (lihat 3.1). Jawabannya mengubah rundown engine.
2. Tambahkan jalur "request lagu → antrean musik" di desain penanganan komentar.
3. Masukkan potongan on air (03:41–11:04 dan 25:07–32:12) dan potongan off air (sekitar 12:00–21:30) ke korpus pembanding kealamian, dengan label register.
4. Untuk rekaman berikutnya, ambil audio langsung dari mixer jika bisa, dan cek ruang penyimpanan atau koneksi supaya rekaman tidak membeku di tengah.

## 5. Keterbatasan
- Transkrip otomatis, tanpa pemisahan pembicara. Nama diri (nama tamu, tempat, kafe) dan angka (misalnya nomor WhatsApp) bisa salah dengar.
- Batas on air dan off air adalah inferensi dari ucapan penyiar dan level audio.
- Komentar dibaca dari frame setiap 10 detik. Komentar yang muncul dan tergeser dalam waktu kurang dari 10 detik bisa terlewat, tetapi risikonya kecil karena trafik komentar sangat rendah.
- Hanya satu sesi program yang berjalan saat ini, dan kebetulan dengan format tamu, sehingga belum mewakili semua variasi sesi live HITS.

## Lampiran (di folder `analisis/`)
- `transkrip_live_2026-10-20.md`: transkrip lengkap dengan stempel waktu dan penanda segmen
- `komentar_tiktok.csv`: log komentar, gift, dan interaksi
- `audio.mp3`: audio mono 16 kHz (10 MB)
- `frames/` (260 JPG) dan `sheets/` (44 lembar kontak dengan stempel waktu)
