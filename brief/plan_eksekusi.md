# Plan Eksekusi — Pengujian Empiris Double Spending pada Bitcoin Core Regtest

Dokumen ini adalah panduan eksekusi lengkap dari awal sampai akhir. Dibaca oleh
pelaksana (manusia + Claude Code) sebelum dan selama membangun proyek.

---

## 1. Tujuan & Pertanyaan Riset

**Tujuan:** mengukur secara empiris tingkat keberhasilan serangan double spending
berbasis fork pada Bitcoin Core (mode regtest), dengan memvariasikan kekuatan
penyerang dan jumlah konfirmasi, lalu membandingkannya dengan prediksi model Nakamoto.

**Pertanyaan Riset:** Bagaimana pengaruh variasi porsi hashrate penyerang dan jumlah
konfirmasi terhadap tingkat keberhasilan serangan double spending berbasis fork pada
Bitcoin Core regtest, dan sejauh mana hasilnya sesuai dengan prediksi model Nakamoto?

---

## 2. Parameter Terkunci (beserta dasar)

| Parameter | Nilai | Dasar literatur |
|---|---|---|
| p (porsi hashrate penyerang) | 0,05 – 0,45, loncatan 0,05 (9 nilai) | Rentang p < 0,5 (Nakamoto 2008; Rosenfeld 2014). Loncatan = resolusi sampling |
| k (jumlah konfirmasi) | 0 – 6 (7 nilai) | Ambang 6 konfirmasi (Nakamoto 2008; Rosenfeld 2014) |
| N (percobaan per kombinasi) | 1.000 | Praktik umum Monte Carlo (Cao et al. 2023; Jiang & Zhang 2024) + hukum bilangan besar |
| Aturan berhenti penyerang | menyerah setelah menambang 20 blok tanpa menyusul | Prinsip: penyerang rasional tak mengejar tanpa batas (Sompolinsky & Zohar 2016). Nilai 20: Rosenfeld 2014 §6 |
| Pre-mine | tidak ada | Penyederhanaan model; penyerang mulai setara |
| Model pembanding | Nakamoto (2008) | Sesuai pertanyaan riset |
| Total percobaan | 9 × 7 × 1.000 = 63.000 | — |

---

## 3. Prinsip Kerja (wajib dipatuhi)

- Kerjakan **berurutan** Tahap 0 → 5. Tahap berikutnya baru mulai setelah tahap
  sebelumnya diverifikasi benar oleh pelaksana manusia.
- Setiap langkah kecil dan bisa diuji. **Tunggu konfirmasi** sebelum lanjut.
- Jangan kirim blok kode panjang sekaligus.
- Saat error, fokus hanya pada bagian bermasalah; jangan regenerasi seluruh solusi.
- Jangan menambah optimasi atau fitur di luar plan ini.
- **Prioritaskan kebenaran logika, bukan sekadar "jalan tanpa error".**
- **BATASAN MUTLAK:** semua eksperimen hanya di jaringan regtest lokal dengan koin
  uji. Dilarang menyentuh mainnet, testnet publik, node pihak lain, atau exchange.

### Standar Penulisan Kode (wajib)

Kode ditujukan untuk dibaca pemula. Utamakan keterbacaan di atas kepintaran.

- **Struktur rapi & modular:** satu file satu tugas (lihat `src/`), satu fungsi satu
  pekerjaan. Jangan menumpuk banyak hal dalam satu fungsi panjang.
- **Nama jelas:** nama variabel dan fungsi menjelaskan maksudnya (mis.
  `tambang_blok_penyerang`, bukan `f1`). Hindari singkatan membingungkan.
- **Komentar penjelas:** beri komentar bahasa Indonesia yang menjelaskan APA dan
  MENGAPA tiap bagian, terutama langkah serangan dan istilah Bitcoin (reorg,
  mempool, konfirmasi). Tujuannya pembaca awam paham tanpa harus tahu Bitcoin.
- **Docstring tiap fungsi:** satu-dua kalimat di awal fungsi menjelaskan tugasnya,
  input, dan output.
- **Langkah bernomor:** di fungsi percobaan (`trial.py`), tandai 6 langkah serangan
  dengan komentar bernomor (# Langkah 1: ... dst) sesuai plan ini.
- **Tanpa trik rumit:** hindari one-liner padat atau pola yang sulit dibaca. Pilih
  kode yang panjang sedikit tapi jelas.
- **Konsisten:** gaya penamaan dan format sama di semua file.

---

## 4. Struktur Folder

```
project-jkkd-bitcoin/
├── CLAUDE.md
├── brief/                   (dokumen panduan)
│   ├── plan_eksekusi.md     (dokumen ini)
│   ├── Dokumentasi.md       (DIBUAT Claude Code di akhir — lihat Tahap 5)
│   └── docs/                (Proposal Ide + 3 paper acuan)
├── config/                  (file konfigurasi 3 node regtest)
├── src/
│   ├── network.py           (nyalakan & sambungkan node)
│   ├── trial.py             (satu percobaan serangan)
│   ├── runner.py            (loop semua kombinasi)
│   └── analysis.py          (hitung metrik, grafik, kurva Nakamoto)
├── results/                 (CSV hasil)
└── figures/                 (grafik)
```

Catatan: `CLAUDE.md` tetap di root agar terbaca otomatis. Dokumen panduan
(`plan_eksekusi.md`, `Dokumentasi.md`) dan paper ada di folder `brief/`.

---

## 5. Definisi Operasional (acuan baku)

- **Undian hashrate:** pada setiap langkah penambangan, blok ditambang oleh penyerang
  dengan peluang p, oleh penambang jujur dengan peluang 1−p. Undian ini berlaku SEJAK
  pembayaran disiarkan, termasuk selama masa konfirmasi (penyerang menambang paralel,
  bukan setelah k konfirmasi). Dasar: ekuivalensi rantai Markov diskrit (Rosenfeld
  2014 §3); desain paralel agar setara model Nakamoto.
- **Reproduksibilitas:** undian memakai seed acak yang tetap dan dicatat di hasil,
  agar eksperimen dapat diulang.
- **Serangan berhasil:** setelah node disatukan kembali dan terjadi reorg, transaksi
  pembayaran ke merchant TIDAK ada di rantai aktif node merchant, sedangkan transaksi
  tandingan penyerang terkonfirmasi. Seri (tie) TIDAK dihitung berhasil.
- **Aturan berhenti:** penyerang berhenti jika sudah menambang 20 blok pada rantai
  rahasia tanpa pernah menyamai/melampaui rantai jujur → percobaan dicatat "gagal".
- **k = 0 (kasus khusus):** merchant menganggap lunas saat transaksi masuk mempool
  (0 konfirmasi). Diperlakukan sebagai titik kontrol, bukan uji langsung ke rumus
  Nakamoto (yang memberi nilai 1 pada k = 0). Definisi sukses tetap sama (tx
  pembayaran tidak ada di rantai akhir).
- **Reset state antar-percobaan:** setiap percobaan harus mulai dari kondisi bersih
  (chain, mempool, wallet) agar hasil tidak tercemar percobaan sebelumnya.

---

## 6. Tahap Eksekusi

### Tahap 0 — Setup
**Kerja:**
- Pasang Bitcoin Core (versi stabil terbaru) dan Python.
- Di macOS, self-sign binary: `xattr -d com.apple.quarantine` lalu `codesign -s -`
  pada file di `bitcoin-*/bin/`.
- Buat struktur folder bagian 4.
**Verifikasi:** jalankan `bitcoind -regtest` sekali, pastikan hidup tanpa error,
lalu matikan.
**Checkpoint manusia:** konfirmasi node bisa nyala.

### Tahap 1 — Jaringan (`src/network.py`)
**Kerja:**
- Siapkan 3 datadir regtest terpisah (merchant, honest, attacker) dengan RPC port
  berbeda.
- Nyalakan 3 `bitcoind -regtest`, sambungkan dengan `addnode`.
- Sediakan fungsi bantu: nyalakan, matikan, sambung, putus
  (`disconnectnode`/`setnetworkactive`), dan reset ke kondisi bersih.
**Verifikasi:** tiap node melihat 2 peer (`getpeerinfo`); blok yang ditambang di satu
node muncul di node lain (`getblockcount` sama setelah sync).
**Checkpoint manusia:** konfirmasi jaringan terbentuk & tersinkron.

### Tahap 2 — Satu percobaan (`src/trial.py`) — INTI
**Desain kunci:** penyerang menambang PARALEL sejak pembayaran disiarkan, bukan
setelah k konfirmasi. Ini wajib agar hasilnya setara model Nakamoto/Rosenfeld dan
perbandingannya sah. (Jika penyerang baru mulai setelah k konfirmasi, ia selalu
tertinggal k blok dan hasilnya menguji skenario yang berbeda dari Nakamoto.)

**Kerja (fungsi yang mengembalikan True/False):**
1. Mulai dari kondisi bersih dengan dana penyerang yang sudah matang (lihat catatan
   efisiensi: danai sekali, pakai ulang; jangan remine 101 blok tiap percobaan).
2. Penyerang menyiapkan pembayaran ke merchant lalu diputus dari jaringan. Transaksi
   pembayaran disiarkan ke rantai publik (node jujur); transaksi tandingan (koin
   kembali ke penyerang) disimpan untuk rantai rahasia.
3. Jalankan undian blok per langkah SEJAK AWAL: tiap blok, dengan peluang p ditambang
   penyerang (menambah rantai rahasia berisi transaksi tandingan), dengan peluang 1−p
   ditambang jujur (menambah rantai publik berisi pembayaran).
4. Merchant menganggap lunas ketika rantai publik memuat k blok di atas pembayaran.
5. Lanjutkan undian sampai rantai rahasia penyerang melampaui rantai publik (penyerang
   menang) ATAU penyerang menyerah (menambang 20 blok tanpa pernah menyusul).
6. Sambungkan penyerang kembali; jaringan memilih rantai terpanjang (reorg bila rantai
   penyerang menang).
7. Cek sukses: di node merchant, transaksi pembayaran hilang dari rantai aktif
   (`getrawtransaction`/`gettransaction`) dan transaksi tandingan terkonfirmasi.
   Verifikasi cabang lama berstatus `valid-fork` via `getchaintips`. Seri = gagal.
**Verifikasi (paling ketat, manual di beberapa percobaan):**
- Transaksi pembayaran TIDAK bocor ke penyerang saat terputus.
- Reorg benar terjadi saat rantai penyerang lebih panjang.
- Transaksi pembayaran benar-benar hilang dari rantai utama (bukan pindah mempool).
**Checkpoint manusia:** konfirmasi satu percobaan menghasilkan berhasil/gagal yang
benar. JANGAN lanjut sebelum ini yakin.

### Tahap 3 — Otomasi (`src/runner.py`)
**Kerja:**
- Loop seluruh kombinasi p (9) × k (7), tiap kombinasi `trial.py` dijalankan 1.000×.
- Reset state tiap percobaan.
- Simpan ke CSV: kolom p, k, nomor_percobaan, hasil (berhasil/gagal), jumlah blok
  yang ditambang penyerang.
**Verifikasi:** jalankan versi kecil dulu (mis. N=10, 2 kombinasi) dan periksa CSV
masuk akal.
**Checkpoint manusia:** konfirmasi loki kecil benar, baru jalankan versi penuh
(63.000 percobaan; boleh ditinggal).

### Tahap 4 — Analisis (`src/analysis.py`)
**Kerja:**
1. Dari CSV, hitung persentase keberhasilan tiap kombinasi (p, k).
2. Buat tabel hasil dan grafik garis: sumbu X = k, satu garis per nilai p.
3. Hitung prediksi model Nakamoto untuk tiap (p, k) dan tambahkan ke grafik.
**Verifikasi:** pola masuk akal — keberhasilan turun saat k naik, naik saat p naik.
**Checkpoint manusia:** konfirmasi tabel & grafik benar.

### Tahap 5 — Kesimpulan & Dokumentasi
**Kerja:**
- Tarik rekomendasi: konfirmasi minimum agar risiko di bawah ambang tertentu per
  nilai p.
- Catat temuan sisi merchant: status transaksi di wallet sebelum vs sesudah reorg.
- Tulis batasan (bagian 7).
- **Buat `brief/Dokumentasi.md`** yang menjelaskan cara kerja proyek dari awal sampai
  akhir sesuai kode final: apa yang dilakukan proyek, istilah dasar, tugas tiap file,
  alur satu percobaan, cara menjalankan (perintah konkret), dan cara membaca hasil.
  Bahasa sederhana untuk pembaca awam, konsisten dengan Standar Penulisan Kode.
**Hasil:** bahan laporan/BAB IV–V + `brief/Dokumentasi.md`.

---

## 7. Batasan yang Wajib Ditulis di Laporan

- Regtest adalah lingkungan terkendali, bukan jaringan nyata; hasil tidak
  merepresentasikan kondisi mainnet (hashrate global, latensi, mempool, fee).
- Hashrate penyerang diemulasikan lewat undian probabilistik, bukan daya tambang
  nyata. Konsekuensinya, eksperimen ini memverifikasi apakah implementasi Bitcoin
  Core nyata sesuai model pada kondisi ideal, bukan mengukur risiko mainnet.
- Penyerang diasumsikan tidak melakukan pre-mine.
- Aturan berhenti penyerang disederhanakan (menyerah setelah 20 blok), mengikuti
  Rosenfeld (2014).
- Untuk sel dengan peluang sangat kecil, N = 1.000 mungkin menghasilkan 0 sukses;
  ini batas resolusi, bukan bukti peluang nol.

---

## 8. Output Akhir

- `results/*.csv` — data mentah 63.000 percobaan.
- `figures/*` — tabel & grafik empiris vs kurva Nakamoto.
- Rekomendasi konfirmasi minimum + temuan sisi merchant.
- Skrip yang dapat direproduksi, berkomentar jelas, mudah dibaca pemula.
- `brief/Dokumentasi.md` DIBUAT oleh Claude Code di Tahap 5 (cara kerja + cara
  menjalankan, sesuai kode final).

---

## 9. Referensi

- Nakamoto, S. (2008). Bitcoin: A Peer-to-Peer Electronic Cash System.
- Rosenfeld, M. (2014). Analysis of Hashrate-Based Double-Spending. arXiv:1402.2009.
- Sompolinsky, Y. & Zohar, A. (2016). Bitcoin's Security Model Revisited. arXiv:1605.09193.
- Cao, T., Decouchant, J. & Yu, J. (2023). Leveraging the Verifier's Dilemma to Double Spend in Bitcoin. FC 2023. arXiv:2210.14072.
- Jiang, Y. & Zhang, J. (2024). Time-Restricted Double-Spending Attack on PoW-based Blockchains. arXiv:2402.17223.
- Hakim, A. R. & Irwanto, D. (2026). Penerapan SHA-256 untuk Analisis Pencegahan Double Spending pada Cryptocurrency Bitcoin. JOAIIA 7(3), 829–840.
- Bitcoin Core, Testing Applications (regtest). developer.bitcoin.org.
