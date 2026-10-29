# Konteks Proyek — Pengujian Empiris Double Spending pada Bitcoin Core Regtest

> Konteks utama proyek untuk Claude Code.
> **Acuan detail & terkunci ada di `brief/plan_eksekusi.md`. Jika ada beda, plan yang berlaku.**

---

## 1. Ringkasan Proyek

Menguji secara empiris keberhasilan serangan **double spending berbasis fork** pada
perangkat lunak Bitcoin asli (**Bitcoin Core**) dalam mode jaringan privat lokal
(**regtest**). Serangan dijalankan berulang dengan memvariasikan kekuatan penyerang dan
jumlah konfirmasi, lalu tingkat keberhasilannya dibandingkan dengan prediksi model Nakamoto.

Konteks akademik: tugas mata kuliah Keamanan Komputer dan Jaringan (JKKD).

---

## 2. Pertanyaan Riset

Bagaimana pengaruh variasi besar hashrate penyerang dan jumlah konfirmasi terhadap tingkat
keberhasilan serangan double spending berbasis fork pada Bitcoin Core regtest, dan sejauh
mana hasilnya sesuai dengan prediksi model Nakamoto?

---

## 3. Research Gap

Acuan utama: Hakim & Irwanto (2026), JOAIIA 7(3). Mereka menguji pencegahan double spending
lewat simulasi Python dengan data sintetis, dan menyarankan penelitian lanjutan memakai
perangkat nyata dan menguji skenario fork. Proyek ini menjawab kedua saran itu.

---

## 4. Ruang Lingkup & Batasan

**Masuk lingkup:** satu objek (Bitcoin Core regtest); satu serangan (double spending berbasis
fork); dua variabel bebas (p dan k).

**Di luar lingkup:** latensi/topologi P2P nyata; race attack 0-konfirmasi berbasis RBF;
perbandingan antar versi/antar blockchain.

**Batasan metodologis (wajib ditulis jujur):**
- Regtest lingkungan terkendali, bukan jaringan nyata (tanpa hashrate global, latensi, mempool nyata).
- Hashrate diemulasikan lewat undian, bukan daya tambang nyata.
- Penyerang tidak melakukan pre-mine; menyerah setelah 20 blok.
- Konsekuensi: hasil memverifikasi apakah implementasi nyata sesuai model pada kondisi ideal,
  bukan mengukur risiko mainnet.

**Batasan etis & hukum (MUTLAK):** semua hanya di regtest lokal dengan koin uji. Dilarang
menyentuh mainnet, testnet publik, node pihak lain, atau exchange.

---

## 5. Variabel Penelitian (terkunci)

| Jenis | Variabel | Nilai | Dasar |
|---|---|---|---|
| Bebas | Porsi hashrate penyerang `p` | 0,05–0,45, loncatan 0,05 (9 nilai) | p<0,5 (Nakamoto; Rosenfeld 2014) |
| Bebas | Jumlah konfirmasi `k` | 0–6 (7 nilai) | Ambang 6 konfirmasi (Nakamoto; Rosenfeld) |
| Terikat | Tingkat keberhasilan double spend | 0–100% | — |
| Kontrol | Jumlah percobaan `N` | 1.000 | Praktik Monte Carlo (Cao 2023; Jiang & Zhang 2024) |
| Kontrol | Aturan berhenti penyerang | menyerah setelah menambang 20 blok tanpa menyusul | Sompolinsky & Zohar 2016; Rosenfeld 2014 §6 |
| Kontrol | Pre-mine | tidak ada | Penyederhanaan model |
| Kontrol | Versi Bitcoin Core | stabil terbaru (dicatat saat setup) | — |

Total: 9 × 7 × 1.000 = 63.000 percobaan.

---

## 6. Rancangan Skenario Serangan (satu percobaan)

**Desain kunci:** penyerang menambang PARALEL sejak pembayaran disiarkan (bukan setelah k
konfirmasi), agar setara model Nakamoto/Rosenfeld dan perbandingannya sah.

1. Siapkan 3 node regtest: merchant, penambang jujur, penyerang.
2. Penyerang menyiapkan pembayaran ke merchant lalu diputus; pembayaran disiarkan ke rantai
   publik, transaksi tandingan (koin kembali ke penyerang) disimpan untuk rantai rahasia.
3. Undian blok per langkah sejak awal: peluang `p` blok milik penyerang (rantai rahasia),
   `1−p` milik penambang jujur (rantai publik). Berlaku juga selama masa konfirmasi.
4. Merchant menganggap sah saat rantai publik memuat `k` blok di atas pembayaran.
5. Lanjutkan sampai rantai rahasia melampaui rantai publik (menang) atau penyerang menyerah
   (20 blok tanpa menyusul).
6. Sambungkan penyerang kembali; jaringan memilih rantai terpanjang (reorg).

**Definisi "berhasil":** transaksi pembayaran hilang dari rantai aktif merchant dan transaksi
tandingan terkonfirmasi. Seri = gagal.

**Reproduksibilitas:** undian memakai seed acak tetap yang dicatat.

---

## 7. Pipeline Eksekusi

0. Setup. 1. Jaringan 3 node. 2. Satu percobaan (bagian 6). 3. Loop p × k × N → CSV.
4. Analisis (metrik, grafik, kurva Nakamoto). 5. Kesimpulan + buat `brief/Dokumentasi.md`.

Detail per tahap ada di `brief/plan_eksekusi.md`.

---

## 8. Metode Analisis Data

1. Persentase keberhasilan tiap kombinasi: berhasil ÷ N × 100%.
2. Tabel + grafik garis (X = konfirmasi, tiap garis = satu nilai p).
3. Bandingkan garis empiris dengan garis prediksi Nakamoto.

Tanpa interval kepercayaan 95% (disederhanakan).

---

## 9. Output yang Diharapkan

Dataset CSV; tabel/grafik empiris vs kurva Nakamoto; rekomendasi konfirmasi minimum; temuan
sisi merchant (status wallet sebelum/sesudah reorg); skrip reproducible berkomentar;
`brief/Dokumentasi.md` (dibuat di Tahap 5).

---

## 10. Paper Acuan

- Hakim & Irwanto (2026). Penerapan SHA-256 untuk Analisis Pencegahan Double Spending. JOAIIA 7(3), 829–840. (gap)
- Nakamoto (2008). Bitcoin: A Peer-to-Peer Electronic Cash System. (pembanding)
- Rosenfeld (2014). Analysis of Hashrate-Based Double-Spending. arXiv:1402.2009.
- Sompolinsky & Zohar (2016). Bitcoin's Security Model Revisited. arXiv:1605.09193. (aturan berhenti)
- Cao, Decouchant & Yu (2023). FC 2023. arXiv:2210.14072. (Monte Carlo)

File ada di folder `ide_dan_referensi/`.

---

## 11. Lingkungan Teknis

- Perangkat: MacBook (Apple Silicon, macOS).
- Bahasa: Python (orkestrasi node via RPC, otomasi, analisis).
- Bitcoin Core: versi stabil terbaru (dicatat saat setup).

---

## 12. Standar Kerja & Kode untuk Claude Code

- Kerjakan per langkah kecil yang bisa diuji; tunggu konfirmasi sebelum lanjut.
- Jangan kirim blok kode panjang sekaligus.
- Saat error, fokus pada bagian bermasalah; jangan regenerasi seluruh solusi.
- Jangan menambah optimasi/fitur di luar plan.
- Kode modular, nama jelas, komentar bahasa Indonesia (apa & mengapa), docstring tiap fungsi,
  langkah serangan bernomor. Mudah dibaca pemula.
- Prioritaskan kebenaran logika, bukan sekadar "jalan tanpa error": pastikan transaksi tidak
  bocor sebelum waktunya, reorg benar terjadi, pembayaran benar hilang. Ini risiko utama.

---

## 13. Istilah Singkat

- **Proof of Work**: penambang menyelesaikan perhitungan berat untuk menambah blok.
- **Konsensus**: kesepakatan otomatis jaringan tentang rantai mana yang sah.
- **Hashrate**: kecepatan komputasi penambang.
- **Konfirmasi**: jumlah blok di atas sebuah transaksi.
- **Double spending**: memakai koin yang sama untuk dua transaksi.
- **Fork**: dua rantai bersaing; yang lebih panjang menang.
- **Reorg**: jaringan berpindah ke rantai lebih panjang, membuang rantai lama.
- **Regtest**: jaringan Bitcoin privat lokal dengan koin uji.
