# Dokumentasi Proyek — Pengujian Empiris Double Spending pada Bitcoin Core Regtest

Dokumen ini menjelaskan cara kerja proyek dari awal sampai Tahap 3, sesuai kode
terakhir di `src/`. Tujuannya: siapa pun yang membuka repo ini (termasuk di laptop
ROG) bisa memahami apa yang sudah dikerjakan, keputusan apa yang sudah diambil, dan
bagaimana melanjutkan run penuh.

Status: **Tahap 0–3 selesai dan teruji di macOS.** Run penuh (63.000 percobaan)
belum dijalankan; rencananya dijalankan di laptop ROG. Tahap 4 (analisis) dan
Tahap 5 (kesimpulan) belum dikerjakan.

Acuan rencana: `brief/plan_eksekusi.md`. Jika ada perbedaan, plan yang berlaku.

---

## 1. Proyek ini tentang apa?

Bitcoin mencegah orang memakai koin yang sama dua kali (double spending) dengan
cara jaringan selalu mengikuti **rantai blok terpanjang**. Tetapi perlindungan ini
tidak mutlak: penyerang yang punya cukup daya tambang bisa diam-diam membangun
rantai tandingan, lalu merilisnya ketika rantainya lebih panjang. Akibatnya,
pembayaran yang sudah "terkonfirmasi" di sisi penjual bisa lenyap.

Proyek ini **menjalankan serangan itu sungguhan** pada perangkat lunak Bitcoin asli
(Bitcoin Core) di jaringan privat lokal (regtest), berulang kali, dengan
memvariasikan:

- **p** — porsi daya tambang (hashrate) penyerang;
- **k** — jumlah konfirmasi yang ditunggu penjual sebelum menganggap lunas.

Tingkat keberhasilan serangan lalu dibandingkan dengan rumus teoretis Nakamoto
(2008). Proyek ini menjawab saran penelitian lanjutan Hakim & Irwanto (2026):
memakai perangkat lunak Bitcoin nyata dan menguji skenario fork.

**Batasan etis:** semua dijalankan hanya di regtest lokal (127.0.0.1) dengan koin
uji. Tidak menyentuh mainnet, testnet publik, node orang lain, atau exchange.

---

## 2. Istilah dasar

| Istilah | Arti sederhana |
|---|---|
| Blok | "Halaman" buku besar Bitcoin berisi sekumpulan transaksi. |
| Rantai blok | Blok-blok yang saling menyambung; tiap blok menunjuk blok sebelumnya. |
| Menambang | Membuat blok baru. Di regtest sangat cepat (tidak perlu daya komputasi besar). |
| Hashrate | Kecepatan menambang. Di proyek ini diemulasikan lewat undian (lihat bagian 4). |
| Konfirmasi | Jumlah blok yang menumpuk di atas transaksi. Blok pemuat transaksi = konfirmasi ke-1. |
| Mempool | Ruang tunggu transaksi yang sudah diterima node tetapi belum masuk blok. |
| UTXO | Koin yang belum dibelanjakan. Satu UTXO hanya boleh dibelanjakan sekali. |
| Double spending | Membelanjakan UTXO yang sama dua kali (ke penjual, lalu kembali ke diri sendiri). |
| Fork | Dua rantai bersaing yang bercabang dari blok yang sama. |
| Reorg | Node pindah ke rantai lain yang lebih panjang; blok di rantai lama dibuang. |
| Regtest | Mode jaringan Bitcoin privat lokal untuk pengujian, dengan koin uji. |
| RPC | Cara skrip Python memberi perintah ke node Bitcoin Core. |
| Node | Satu program `bitcoind` yang menjalankan Bitcoin Core. |

---

## 3. Parameter terkunci

| Parameter | Nilai | Dasar |
|---|---|---|
| p (porsi hashrate penyerang) | 0,05–0,45, loncatan 0,05 (9 nilai) | p < 0,5 (Nakamoto 2008; Rosenfeld 2014) |
| k (konfirmasi) | 0–6 (7 nilai) | Ambang 6 konfirmasi (Nakamoto; Rosenfeld) |
| N (percobaan per kombinasi) | 1.000 | Praktik Monte Carlo (Cao et al. 2023; Jiang & Zhang 2024) |
| Total percobaan | 9 × 7 × 1.000 = 63.000 | — |
| Aturan berhenti | penyerang menyerah setelah menambang 20 blok tanpa menyusul | Sompolinsky & Zohar 2016; nilai 20 dari Rosenfeld 2014 §6 |
| Pre-mine | tidak ada | Penyederhanaan model |
| Seri (rantai sama panjang) | dihitung GAGAL | Definisi operasional plan |
| Model pembanding | Nakamoto (2008), dengan z = k | Pertanyaan riset |
| Seed acak | `2026`; seed per percobaan `"2026\|p=0.05\|k=0\|i=0"` | Reproduksibilitas |
| Bitcoin Core | v32.1.0 (paket resmi, checksum SHA256 diverifikasi) | Versi stabil terbaru saat setup |

---

## 4. Cara kerja satu percobaan

Ada 3 node di satu laptop, masing-masing dengan port sendiri dan hanya bisa diakses
dari 127.0.0.1:

- **merchant** — penjual yang menerima pembayaran;
- **honest** — penambang jujur yang menambang rantai publik;
- **attacker** — penyerang.

**Desain paralel (keputusan "b"):** penyerang mulai menambang rantai rahasia SEJAK
pembayaran disiarkan, termasuk selama penjual menunggu konfirmasi. Ini wajib agar
setara dengan model Nakamoto. (Jika penyerang baru mulai setelah k konfirmasi, ia
selalu tertinggal k blok dan yang diuji adalah skenario lain.)

Satu percobaan (`trial.jalankan_satu_percobaan`) terdiri dari 7 langkah:

1. **Reset ke baseline didanai.** Ketiga node dikembalikan ke kondisi tersimpan:
   rantai setinggi 101 blok, penyerang punya tepat satu koin matang 50 BTC.
2. **Fase pembuka.**
   - Penyerang membuat dua transaksi dari koin yang SAMA, lewat raw transaction
     (`createrawtransaction` + `signrawtransactionwithwallet`):
     - **tx A**: 10 BTC ke merchant + 39,9999 BTC kembalian ke penyerang;
     - **tx B**: 49,9999 BTC kembali ke penyerang (tandingan).
     Fee keduanya sama: 0,0001 BTC.
   - Penyerang **diputus** dari jaringan (`setnetworkactive false`).
   - tx A dikirim langsung ke merchant dan honest.
   - Cek anti-bocor: tx A ada di mempool merchant & honest, mempool penyerang
     kosong, tx B tidak ada di mempool mana pun, semua node masih di titik fork.
3. **Undian blok.** Tiap langkah satu blok ditambang: dengan peluang p oleh
   penyerang (rantai rahasia), selain itu oleh honest (rantai publik). tx B masuk
   blok penyerang pertama; tx A masuk blok honest pertama kapan pun terjadi; blok
   lainnya kosong. Blok dibuat dengan `generateblock` agar isinya pasti.
4. **Lunas.** Merchant menganggap lunas saat tx A punya k konfirmasi (n ≥ k).
   Untuk k = 0, lunas saat tx A masuk mempool. Konfirmasi dicek langsung di wallet
   merchant.
5. **Kapan berhenti** (dicek setelah tiap blok, MENANG dicek lebih dulu):
   - menang: n ≥ k **dan** m > n (m = blok penyerang, n = blok honest);
   - berhenti awal: n ≥ 20 (penyerang sudah pasti gagal, lihat temuan T5);
   - menyerah: m ≥ 20 dan m ≤ n.
6. **Penyerang disambung kembali.** Sebelumnya dicek lagi: tinggi kedua rantai
   cocok dengan m dan n, blok rahasia belum bocor, blok publik belum sampai ke
   penyerang. Lalu jaringan memilih rantai terpanjang (reorg bila penyerang menang).
7. **Penentuan sukses di node merchant.** Berhasil jika SEMUA benar:
   - blok pemuat tx B ada di rantai aktif merchant;
   - tx A hilang: blok pemuatnya tidak di rantai aktif DAN tx A tidak kembali ke
     mempool;
   - cabang publik lama berstatus `valid-fork` di `getchaintips` (dilewati bila
     n = 0, karena tidak ada cabang publik).

   **Cek silang:** hasil ini harus sama dengan hasil undian. Jika berbeda, itu
   tanda bug, dan percobaan berhenti dengan `GalatVerifikasi` (tidak dicatat).

Gambaran sederhana (contoh k = 2, urutan undian J P P J P → penyerang menang):

```
titik fork (blok 101)
 ├─ rantai publik  (honest):  [A] [-]            ← tx A di blok pertama
 └─ rantai rahasia (attacker): [B] [-] [-]       ← tx B di blok pertama
Setelah disambung: rantai rahasia (3 blok) > publik (2 blok) → reorg,
tx A lenyap dari rantai merchant, tx B terkonfirmasi.
```

---

## 5. Tugas tiap file

```
config/
  merchant.conf, honest.conf, attacker.conf   konfigurasi 3 node (regtest=1, port,
                                              hanya 127.0.0.1, tanpa Tor/peer otomatis)
src/
  network.py   nyalakan/matikan node, RPC, sambung/putus penyerang, sinkronisasi,
               reset (bersih total & ke baseline didanai)
  trial.py     baseline didanai, pembuatan tx A/tx B, cek anti-bocor, undian
               paralel, penentuan sukses, satu percobaan utuh (Langkah 1–7)
  runner.py    loop p × k × N, CSV inkremental, resumable, progres + perkiraan waktu
  jaga_runner.py  menjalankan runner.py dan menyalakannya lagi bila crash,
               sambil menyimpan bukti ke ..\bukti_crash_<waktu> (T13)
brief/
  plan_eksekusi.md   rencana & parameter terkunci
  CLAUDE.md          konteks proyek
  Dokumentasi.md     dokumen ini
```

Folder yang dibuat otomatis saat berjalan (tidak masuk repo):

- `bitcoin-32.1/` — program Bitcoin Core (dipasang manual, lihat bagian 8);
- `node_data/` — data ketiga node yang sedang berjalan (aman dihapus);
- `node_data_baseline/` — salinan baseline didanai (dibuat ulang otomatis oleh
  runner di awal tiap sesi dan tiap 20 jam, lihat T10);
- `results/` — CSV hasil.

Kode `src/` hanya memakai pustaka standar Python (tanpa paket tambahan).

---

## 6. Progres per tahap

### Tahap 0 — Setup
- Bitcoin Core **v32.1.0** (`bitcoin-32.1-arm64-apple-darwin.tar.gz`) diunduh dari
  bitcoincore.org; checksum SHA256 cocok dengan `SHA256SUMS` resmi.
- Binari macOS di-self-sign (`xattr -d com.apple.quarantine`, `codesign -s -`).
- Verifikasi: `bitcoind -regtest` menyala dengan `chain=regtest`, lalu dimatikan.
- Python 3.11.9.

### Tahap 1 — Jaringan (`network.py`)
| Langkah | Isi | Hasil uji |
|---|---|---|
| 1.1 | Konfigurasi 3 node, nyalakan/matikan | 3 node `chain=regtest`, port hanya 127.0.0.1 |
| 1.2 | Sambung (`addnode onetry`), putus penyerang (`setnetworkactive false`) | Tiap node 2 peer; setelah diputus penyerang 0 peer, merchant–honest tetap 1 peer; tidak tersambung ulang otomatis; sambungan paksa ke penyerang ditolak |
| 1.3 | Sinkronisasi (`tunggu_sinkron` membandingkan hash ujung rantai) | Blok menyebar saat tersambung; saat terisolasi blok tidak menyeberang dua arah; setelah disambung jaringan menyatu ke rantai terpanjang |
| 1.4 | Reset bersih total | Kembali ke genesis, mempool & wallet kosong, ~1–1,6 detik |

### Tahap 2 — Satu percobaan (`trial.py`)
| Langkah | Isi | Hasil uji |
|---|---|---|
| 2.1 | Baseline didanai (dibuat sekali, ~13 detik) + reset ke baseline (salin datadir) | Tinggi 101, penyerang 1 koin 50 BTC; reset ~2,3 detik |
| 2.2 | tx A & tx B dari UTXO yang sama | Input identik, txid beda; masing-masing lolos `testmempoolaccept`, bersama ditolak (`conflict-in-package`); belum tersiar |
| 2.3 | Fase pembuka + cek anti-bocor | Lolos; 5 jenis kebocoran yang sengaja dibuat semuanya terdeteksi |
| 2.4 | Undian paralel | 7 kasus batas dengan urutan undian paksa lolos; 1,26 juta urutan acak membuktikan berhenti-awal tidak mengubah hasil |
| 2.5 | Penyatuan & penentuan sukses + percobaan utuh | Menang (reorg 2 dan 6 blok), kalah, k = 0, dan 3 skenario ketidakcocokan (berhenti dengan galat) lolos; seed sama → hasil identik |

### Tahap 3 — Otomasi (`runner.py`)
- Loop p × k × N, reset ke baseline tiap percobaan, CSV inkremental, resumable,
  progres berkala.
- `network.py` dibuat OS-agnostic: node dijalankan lewat `subprocess.Popen`
  (opsi `-daemon` tidak ada di Windows), nama `bitcoind.exe` di Windows, node di
  kelompok proses sendiri agar Ctrl+C hanya mengenai Python, dan proses node
  "dipungut" agar tidak menumpuk sebagai zombie.
- **Uji kecil di Mac** (p = 0,05 & 0,45; k = 0 & 3; N = 20 → 80 percobaan):

  | Kombinasi | Berhasil |
  |---|---|
  | p = 0,05, k = 0 | 3/20 |
  | p = 0,05, k = 3 | 0/20 |
  | p = 0,45, k = 0 | 19/20 |
  | p = 0,45, k = 3 | 13/20 |

  Rata-rata **5,9 detik per percobaan** (Mac Apple Silicon).
- **Uji resume:** run dihentikan dengan Ctrl+C dua kali (salah satunya tepat saat
  node sedang dinyalakan), lalu dimatikan paksa (SIGKILL), lalu sengaja ditambah
  baris CSV terpotong. Hasil:
  - setelah Ctrl+C tidak ada bitcoind tertinggal;
  - setelah SIGKILL satu bitcoind sempat tertinggal (Python mati seketika sehingga
    tidak bisa membersihkan), dan dimatikan otomatis oleh sesi berikutnya;
  - baris terpotong dibuang otomatis; setiap sesi melanjutkan dari posisi terakhir
    ("Sudah selesai sebelumnya: 10/80 … 15/80 … 25/80");
  - CSV akhir **identik baris demi baris** dengan run tanpa gangguan, tanpa
    duplikat.

---

## 7. Keputusan & temuan penting

**T1. Desain paralel (b).** Penyerang menambang sejak pembayaran disiarkan, agar
setara model Nakamoto/Rosenfeld (bagian 4).

**T2. Tiap node menambang ke alamatnya sendiri.** Saat uji 1.3, penyerang dan
honest yang menambang ke coinbase yang sama, di atas blok induk yang sama, dalam
detik yang sama menghasilkan blok yang **identik byte demi byte** (hash sama).
Satu blok bisa "terhitung" di dua rantai dan merusak hasil. Karena itu alamat
penambang selalu milik wallet node masing-masing (dan isi blok penyerang/honest
juga berbeda karena memuat tx B/tx A).

**T3. Cek `valid-fork` di node merchant.** Status cabang yang kalah berbeda antar
node: di node yang tidak pernah memvalidasi blok lengkapnya, cabang itu tampil
`headers-only`. Merchant adalah node yang melihat rantai publik penuh, jadi cek
dilakukan di sana.

**T4. Temuan RBF (Bitcoin Core v32).** Ketika tx A sudah di mempool, tx B ditolak
dengan alasan `insufficient fee`: v32 menganggap transaksi yang konflik sebagai
upaya penggantian (replace-by-fee). Seandainya tx B masuk mempool dengan fee lebih
tinggi, ia bisa menggantikan tx A tanpa fork — itu *race attack* 0-konfirmasi yang
di luar lingkup. Karena itu tx B **tidak pernah** masuk mempool mana pun (hanya
disisipkan langsung ke blok rahasia) dan fee tx A = fee tx B. Desain tetap murni
serangan berbasis fork.

**T5. "Menyerah" tidak pernah tercapai.** Aturan menyerah (m ≥ 20 dan m ≤ n)
hanya bisa terpenuhi jika n ≥ 20, padahal pada saat n mencapai 20 berhenti-awal
sudah terpicu. Diuji pada 1,26 juta urutan acak: hasil menang/gagal **identik**
dengan dan tanpa berhenti-awal (0 perbedaan). Implikasi:
1. Di CSV, semua kegagalan tercatat `berhenti_awal`.
2. Secara efektif aturan 20 blok = "serangan gagal bila rantai jujur mencapai 20
   blok lebih dulu".
3. **Cara baca grafik:** rumus Nakamoto mengasumsikan perlombaan tanpa batas,
   sedangkan di sini perlombaan dipotong di 20 blok. Hasil empiris bisa sedikit di
   bawah kurva Nakamoto, paling terlihat di p = 0,45. Ini akibat aturan berhenti,
   bukan kesalahan implementasi.

**T6. Sisi merchant: `walletconflicts` kosong, konfirmasi menjadi negatif.**
- Wallet merchant hanya menyimpan transaksi yang menyentuh alamatnya. tx B tidak
  membayar merchant, sehingga tidak pernah masuk wallet merchant dan
  `walletconflicts` tetap kosong.
- Konflik terlihat lewat **konfirmasi negatif** tx A, yang besarnya sama dengan
  konfirmasi tx B (contoh: 2 → −3 saat m = 3; 6 → −7 saat m = 7).
- Saldo merchant: pada k ≥ 1 saldo *terpercaya* 10 BTC turun menjadi 0 setelah
  reorg; pada k = 0, 10 BTC hanya tampil sebagai saldo *tertunda*
  (`untrusted_pending`), lalu menjadi 0. Artinya wallet merchant sempat
  menyatakan dana "terpercaya" sebelum dana itu lenyap.

**T7. Pelajaran sinkronisasi.** Saat membuat baseline, honest sempat menambang
sebelum menerima blok penyerang, sehingga terjadi fork tak disengaja dan dana
penyerang hilang. Perbaikan dan aturan umum: **setiap kali urutan blok penting,
tunggu sinkron dulu.**

**T8. Konvensi k dan pembanding.** Blok pemuat tx A = konfirmasi ke-1; merchant
lunas saat konfirmasi ≥ k. Kurva Nakamoto di Tahap 4 memakai z = k dengan
konvensi yang sama. k = 0 adalah titik kontrol (rumus Nakamoto memberi 1 di
k = 0).

**T9. Waktu.** Reset ke baseline ~2,3 detik (sebagian besar untuk menyalakan
ulang node); tiap blok ~0,17 detik. Rata-rata ~5,9 detik per percobaan →
run penuh ±103 jam (±4,3 hari) jika mesin secepat Mac uji. Keputusan: N tetap
1.000, run penuh di ROG.

**T10. Umur baseline harus di bawah 24 jam (ditemukan saat run penuh di ROG).**
Blok di baseline memakai waktu saat baseline dibuat. Setelah 21.006 percobaan,
saat baseline berumur ±30 jam, percobaan p = 0,20, k = 0, i = 6 (penyerang
menang 1–0) berhenti dengan `TimeoutError` di `tunggu_sinkron`: setelah
penyerang disambung kembali, merchant dan honest tidak meminta blok penyerang.
- **Penyebab:** Bitcoin Core dengan setting default menganggap node yang ujung
  rantainya lebih tua dari 24 jam sedang *Initial Block Download* (IBD). Dalam
  mode itu node hanya meminta header dari satu peer. Di `debug.log`, merchant
  dan honest tidak pernah keluar dari IBD; penyerang keluar hanya karena
  menambang blok sendiri.
- **Bukti:** dengan baseline lama galat terulang persis; dengan baseline baru
  percobaan yang sama lolos.
- **Penanganan:** `runner.py` membuat ulang baseline didanai (fungsi yang sama,
  `trial.buat_baseline_didanai`) di awal tiap sesi dan setiap 20 jam, dan
  mencetak satu baris log tiap kali. Konfigurasi node **tidak** diubah (tidak
  memakai `-maxtipage`), karena yang diuji adalah Bitcoin Core dengan setting
  default; yang dikelola hanya baseline sebagai fixture. `trial.py`, seed, dan
  format CSV tidak berubah.
- **Uji penanganan** (salinan terpisah, ambang dipendekkan menjadi 60 detik,
  dimulai dari baseline lama ±30 jam): 60 percobaan, baseline dibuat ulang 5 kali
  (1 di awal sesi + 4 di tengah run), tanpa galat. Dari 60 baris, 46 yang sudah
  ada di CSV run penuh **identik** (0 berbeda), termasuk p = 0,20, k = 0,
  i = 0–2; i = 6 lolos dengan hasil `True, m = 1, n = 0, menang`.
- **Dampak ke hasil:** tidak ada. Hasil tiap percobaan ditentukan undian (seed)
  dan diverifikasi silang di node merchant, sehingga baseline baru (hash blok
  dan alamat berbeda) memberi baris CSV yang sama. Galat ini juga tidak bisa
  menghasilkan baris salah: percobaan yang tidak sinkron berhenti sebelum
  dicatat, sehingga 21.006 baris sebelum galat tetap valid.

**T11. TCP self-connect di port RPC (Windows, ditemukan saat run penuh di ROG).**
Sekitar pukul 02.00 WIB tanggal 1 Nov run berhenti dengan
`http.client.BadStatusLine: POST / HTTP/1.1` saat memanggil RPC, diikuti
`subprocess.TimeoutExpired` di `matikan_node` (bitcoind merchant tidak keluar
dalam 30 detik). Waktu pasti dan `debug.log` saat crash tidak bisa dipulihkan:
sesi berikutnya menimpa `node_data/` dan waktu ubah CSV.
- **Penyebab:** rentang port dinamis (port asal otomatis) Windows di ROG adalah
  **1024–65535**, bukan bawaan Windows 49152–65535 (di macOS mulai 49152).
  Port proyek 18501–18503 dan 18601–18603 berada di dalamnya. Saat bitcoind
  belum/tidak mendengarkan port RPC-nya (sedang menyala atau mati), Windows
  sesekali memberi port tujuan itu sendiri sebagai port asal, sehingga socket
  tersambung ke dirinya sendiri: Python mengirim `POST / HTTP/1.1` dan membaca
  request-nya sendiri sebagai jawaban. `BadStatusLine` bukan `OSError`, jadi
  tidak ditangkap pengulangan di `tunggu_rpc_siap` dan runner berhenti.
  `TimeoutExpired` adalah gejala lanjutan saat runner membereskan node.
- **Bukti:**
  1. Bukan sleep: Windows di ROG mencatat sleep/Modern Standby (event
     Kernel-Power 42/107/506/507), tetapi event Kernel-Power terakhir adalah
     30 Okt 14:14:50, sebelum run penuh dimulai; tidak ada reboot sejak 29 Okt.
  2. Bukan rebutan sumber daya: tidak ada event Resource-Exhaustion, tidak ada
     error/warning di log Application, Reliability Monitor hanya mencatat
     pembaruan Defender, dan puncak pagefile sejak boot 3,9 dari 14 GB.
  3. Socket yang disambungkan ke dirinya sendiri lalu dikirimi request seperti
     `panggil_rpc` menghasilkan galat yang sama persis:
     `http.client.BadStatusLine: 'POST / HTTP/1.1\r\n'`.
  4. Dari 100.000 permintaan port otomatis, 200 jatuh di 18500–18699 dan 6 tepat
     di port proyek.
- **Perbaikan lapis 1 (lingkungan):** blok 18500–18699 dikecualikan dari
  kumpulan port asal otomatis Windows (perlu admin, bertahan setelah reboot):
  ```
  netsh int ipv4 add excludedportrange protocol=tcp startport=18500 numberofports=200
  ```
  Rentang port dinamis global **tidak** diubah (tetap 1024–65535), karena belum
  diketahui program apa yang menyetelnya. Bitcoin Core dan konfigurasinya juga
  tidak diubah. Pembatalan:
  `netsh int ipv4 delete excludedportrange protocol=tcp startport=18500 numberofports=200`.
- **Perbaikan lapis 2 (kode):** `tunggu_rpc_siap` di `network.py` juga menangkap
  `http.client.HTTPException` (induk `BadStatusLine`) dan memperlakukannya
  sebagai "node belum siap", sehingga dicoba lagi. `trial.py`, `runner.py`,
  seed, format CSV, dan konfigurasi node tidak berubah.
- **Uji perbaikan:**
  1. Sesudah exclusion, dari 100.000 permintaan port otomatis **0** jatuh di
     18500–18699 (sebelumnya 200).
  2. Bind eksplisit dan listen di 18501 tetap bisa, jadi bitcoind tetap bisa
     memakai port proyek. (Self-connect dengan bind eksplisit masih mungkin,
     tetapi itu tidak pernah dilakukan klien; crash berasal dari port otomatis.)
  3. Uji unit: `panggil_rpc` palsu yang melempar `BadStatusLine` dua kali.
     Kode lama langsung gagal di panggilan pertama; kode baru mencoba lagi dan
     berhasil di panggilan ketiga.
  4. Uji nyata di salinan terpisah yang port-nya berada di dalam blok yang
     dikecualikan: 20 percobaan tanpa galat, **20/20 identik** dengan CSV run
     penuh.
- **Dampak ke hasil:** tidak ada. Percobaan yang crash tidak tercatat (baris
  hanya ditulis setelah lolos verifikasi). Baris yang sudah ada tetap valid,
  dan run dilanjutkan dari 24.571 baris.

**T12. File baseline dikunci proses lain saat node menyala (Windows, ROG).**
Pukul 10.52 WIB tanggal 1 Nov run berhenti dengan
`TimeoutError: Node merchant tidak siap dalam 30 detik` saat reset ke baseline
(setelah p=0.20 k=4 i=727, 25.728 baris).
- **Penyebab:** `debug.log` merchant (disalin sebelum run diulang) menunjukkan
  bitcoind keluar di detik yang sama ia dinyalakan:
  ```
  Fatal LevelDB error: IO error: ...\merchant\regtest\blocks\index/000004.dbtmp:
  Unable to remove the file to be replaced.
  Error opening block database.
  ```
  Saat membuka database blok, LevelDB mengganti file `CURRENT` lewat file
  `.dbtmp`; penggantian gagal karena file yang baru disalin dari baseline sedang
  dibuka proses lain. Runner tidak memeriksa apakah proses masih hidup, jadi ia
  tetap menunggu RPC selama 30 detik lalu melapor timeout. Proses pengunci
  tidak bisa dipastikan setelah kejadian. Kandidat terkuat: pemindaian
  real-time Windows Defender (aktif) dan Windows Search Indexer (aktif dan
  mengindeks folder Downloads); keduanya membuka file yang baru ditulis. Crash
  pukul 09.21 dengan gejala sama kemungkinan berpenyebab sama, tetapi log-nya
  sudah tertimpa.
- **Perbaikan lapis 1 (lingkungan):** `node_data` dan `node_data_baseline`
  dikecualikan dari pemindaian Defender (PowerShell admin), dan folder proyek
  dikeluarkan dari Windows Search lewat Indexing Options → Modify:
  ```
  Add-MpPreference -ExclusionPath "C:\Users\arvin\Downloads\bitcoin-hash\node_data","C:\Users\arvin\Downloads\bitcoin-hash\node_data_baseline"
  ```
  Pembatalan: `Remove-MpPreference -ExclusionPath ...` dengan path yang sama.
- **Perbaikan lapis 2 (kode, `network.py`):** `tunggu_rpc_siap` melempar
  `GalatNodeKeluar` begitu proses bitcoind sudah keluar, tanpa menunggu 30
  detik. `reset_ke_baseline` menangkapnya, menyalin `node_data` ke
  `..\bukti_crash_<waktu>` sebagai bukti, mencetak satu baris peringatan, lalu
  mengulang dari salinan baseline baru (maksimal 3 kali menyala; setelah itu
  galat dilempar dan run berhenti). `trial.py`, `runner.py`, seed, format CSV,
  dan konfigurasi node tidak berubah.
- **Uji perbaikan** (salinan terpisah, port 18511–18513/18611–18613; file
  `CURRENT` merchant sengaja dibuka 1,5 detik setelah baseline disalin):
  1. Galat yang muncul di `debug.log` sejenis dengan aslinya (`Fatal LevelDB
     error ... being used by another process`, `Error opening block database`).
  2. Dikunci sekali: node keluar terdeteksi, bukti tersalin, reset diulang, dan
     percobaan p=0.05 k=0 i=1 selesai dengan hasil `True, 1, 0, menang`,
     **identik** dengan baris di CSV run penuh.
  3. Dikunci tiga kali berturut-turut: dua peringatan, lalu `GalatNodeKeluar`
     dilempar dalam 11,5 detik; tidak ada bitcoind tertinggal.
- **Dampak ke hasil:** tidak ada. Kegagalan terjadi saat reset, sebelum
  percobaan dimulai, dan undian ditentukan oleh seed, sehingga percobaan yang
  diulang menghasilkan baris yang sama. Run dilanjutkan dari 25.728 baris.
- **Kejadian ulang & perbaikan lanjutan (2 Nov 08.51 WIB):** kuncian terjadi
  lagi walaupun pengecualian Defender/Search aktif (honest:
  `chainstate/000004.dbtmp: Unable to remove the file to be replaced`), jadi
  ada proses lain yang ikut mengunci. Saat itu merchant sudah menyala, dan
  penyalinan bukti di lapis 2 gagal (`shutil.Error`, file merchant terkunci)
  sehingga pengulangan tidak berjalan; penjaga (T13) juga ikut berhenti karena
  nama folder buktinya bentrok di detik yang sama. Run diam ±40 menit.
  Perbaikan: node yang sudah menyala dimatikan dulu sebelum bukti disalin;
  gagal menyalin bukti hanya dicetak sebagai peringatan; nama folder bukti
  diberi akhiran `_2`, `_3`, ... bila sudah ada (`folder_bukti_baru`); penjaga
  tetap menyalakan ulang walaupun bukti gagal disimpan. Uji di salinan
  terpisah: kode lama mereproduksi `shutil.Error` yang sama; kode baru
  mengulang reset dan percobaan selesai dengan hasil identik CSV run penuh;
  batas 3 kali tetap berlaku tanpa bitcoind tertinggal.

**T13. Merchant melihat 3 peer setelah penyerang disambung kembali (ROG).**
Sekitar pukul 14.13 WIB tanggal 1 Nov (setelah heartbeat 28.008/63.000,
p=0.25 k=0) run berhenti di `sambungkan_kembali_penyerang` dengan
`TimeoutError: Node merchant punya 3 peer, diharapkan 2`: selama 10 detik
merchant memegang satu koneksi lebih banyak dari seharusnya.
- **Penyebab:** belum terbukti. Run dijalankan ulang sebelum `node_data`
  disalin, sehingga log saat crash tertimpa. Selain itu, `debug.log` bawaan
  hanya mencatat koneksi keluar ("New manual peer connected"); koneksi masuk
  dan pemutusan tidak tercatat tanpa `-debug=net` (konfigurasi node sengaja
  tidak diubah).
- **Penanganan (operasional, bukan perbaikan akar masalah):** `jaga_runner.py`
  menjalankan `runner.py`; bila runner crash, `node_data` dan pesan galat
  disalin ke `..\bukti_crash_<waktu>`, lalu runner dinyalakan lagi setelah 30
  detik (resumable). Penjaga tidak menyalakan ulang bila run selesai, bila
  Ctrl+C, bila muncul `GalatVerifikasi`, atau bila 3 sesi berturut-turut crash
  tanpa baris baru. `trial.py`, `runner.py`, `network.py`, seed, format CSV,
  dan konfigurasi node tidak berubah.
- **Uji penjaga:**
  1. Salinan terpisah (port 1851x/1861x), 12 percobaan p=0.05 k=0; bitcoind
     merchant dimatikan paksa di tengah percobaan. Penjaga mencatat crash,
     menyimpan bukti (galat + `node_data`), menyalakan runner lagi, dan run
     selesai normal. Ke-12 baris **identik** dengan CSV run penuh; tidak ada
     bitcoind tertinggal.
  2. Uji unit dengan sesi palsu: crash lalu selesai → 2 sesi; `GalatVerifikasi`
     → berhenti; Ctrl+C → berhenti; crash tanpa kemajuan → berhenti setelah 3
     sesi.
  3. Perbaikan 2 Nov: versi pertama penjaga berhenti membaca stderr runner
     setelah Ctrl+C. Traceback runner memenuhi pipe, runner macet menulis, dan
     penjaga macet menunggu runner (Ctrl+C kedua tidak menolong di Windows).
     Kini stderr tetap dibaca sampai habis. Simulasi (traceback palsu 200 KB
     setelah Ctrl+C tiruan): versi lama macet sampai dihentikan paksa, versi
     baru selesai dalam 2,1 detik. Pada kejadian nyata, node sudah dimatikan
     runner dan baris CSV terakhir utuh sebelum proses yang macet dihentikan.
- **Dampak ke hasil:** tidak ada. Percobaan yang crash (p=0.25 k=0 i=8) tidak
  tercatat dan diulang setelah run dijalankan lagi; validasi 28.034 baris: 0
  duplikat, 0 masalah. Bila crash ini berulang, bukti dari penjaga dipakai
  untuk mencari akar masalahnya.

---

## 8. Menjalankan run penuh di ROG

Kode sudah dibuat OS-agnostic, tetapi **baru diuji di macOS**. Karena itu
jalankan uji kecil dulu (langkah 5) sebelum run penuh.

### 8.1 Siapkan Python
- Pasang Python 3.11 (atau lebih baru). Tidak perlu paket tambahan untuk
  `runner.py`.

### 8.2 Ambil kode
```
git clone https://github.com/dzackyahmad/bitcoin-hash.git
cd bitcoin-hash
```

### 8.3 Pasang Bitcoin Core v32.1 (versi yang sama dengan uji di Mac)
Unduh dari `https://bitcoincore.org/bin/bitcoin-core-32.1/`:

- **Windows:** `bitcoin-32.1-win64.zip` dan `SHA256SUMS`.
  Cek checksum (PowerShell):
  ```
  Get-FileHash bitcoin-32.1-win64.zip -Algorithm SHA256
  ```
  Bandingkan dengan baris `bitcoin-32.1-win64.zip` di `SHA256SUMS`.
- **Linux:** `bitcoin-32.1-x86_64-linux-gnu.tar.gz`; cek dengan
  `sha256sum --ignore-missing -c SHA256SUMS`.

Ekstrak ke **root repo** sehingga programnya berada di:
- Windows: `bitcoin-32.1\bin\bitcoind.exe`
- Linux: `bitcoin-32.1/bin/bitcoind`

(Folder ini sengaja tidak ada di repo karena besar.) Jika Windows Firewall
bertanya, akses cukup untuk jaringan privat; node hanya memakai 127.0.0.1.

**Khusus Windows, cek rentang port dinamis (T11):**
`netsh int ipv4 show dynamicport tcp`. Jika rentangnya mencakup port proyek
(18501–18503, 18601–18603), mis. mulai dari 1024, kecualikan blok proyek
dari port asal otomatis dengan PowerShell admin:
```
netsh int ipv4 add excludedportrange protocol=tcp startport=18500 numberofports=200
```
Hentikan run dulu sebelum menjalankannya: Windows bisa menolak exclusion bila
ada port di blok itu yang sedang dipakai.

**Khusus Windows, kecualikan folder data node dari antivirus & pengindeks (T12):**
PowerShell admin:
`Add-MpPreference -ExclusionPath "<repo>\node_data","<repo>\node_data_baseline"`,
lalu keluarkan folder repo dari Indexing Options → Modify.

### 8.4 Cegah laptop tidur
Run penuh berjalan berhari-hari. Atur power plan agar laptop tidak sleep/hibernate
saat dicolok listrik.

### 8.5 Uji kecil dulu (±8 menit)
Dari root repo:
```
python src/runner.py --p 0.05 0.45 --k 0 3 --n 20 --csv results/uji_kecil.csv
```
Baseline didanai dibuat ulang otomatis di awal tiap run (~6–15 detik), lalu
tiap 20 jam selama run (lihat T10).

**Cek reproduksibilitas lintas mesin:** seed bersifat deterministik, jadi baris
CSV di ROG harus **sama persis** dengan hasil di Mac. Contoh baris dari Mac:
```
0.05,0,0,True,1,0,menang,2026|p=0.05|k=0|i=0
0.05,3,1,False,3,20,berhenti_awal,2026|p=0.05|k=3|i=1
0.45,0,0,True,3,2,menang,2026|p=0.45|k=0|i=0
0.45,3,1,False,12,20,berhenti_awal,2026|p=0.45|k=3|i=1
0.45,3,19,True,11,10,menang,2026|p=0.45|k=3|i=19
```
Jumlah berhasil per kombinasi juga harus sama dengan tabel di bagian 6
(Tahap 3): 3/20, 0/20, 19/20, 13/20. Jika berbeda, **jangan lanjut run penuh** —
catat perbedaannya dan periksa dulu.

### 8.6 Run penuh
```
python src/runner.py
```
- Hasil ditulis ke `results/hasil_percobaan.csv`, satu baris per percobaan.
- Progres (heartbeat) dicetak tiap 10 percobaan, contoh:
  `[2026-10-30 15:02:11] global 1240/63000 (2.0%) | sel (0.05, 1) 240/1000 | laju 0.169 trial/dtk | ETA 101:13:25`
  (waktu, posisi global, posisi di sel (p, k), laju percobaan per detik, perkiraan sisa waktu).
- **Ditinggal tanpa ditunggui:** jalankan lewat penjaga,
  `python src/jaga_runner.py` (argumen sama dengan runner). Bila runner crash,
  bukti disimpan ke `..\bukti_crash_<waktu>` dan runner dinyalakan lagi otomatis
  (T13). Baris penjaga diawali `[jaga]`.
- **Jika berhenti** (Ctrl+C, listrik mati, restart Windows): jalankan ulang
  perintah yang sama. Runner membaca CSV, melewati percobaan yang sudah tercatat,
  membuang baris terakhir bila terpotong, mematikan node sisa, lalu melanjutkan.
- Baseline didanai dibuat ulang di awal tiap sesi dan tiap 20 jam (T10). Tiap
  kali terjadi, tercetak satu baris, contoh:
  `[2026-10-31 20:29:51] baseline didanai dibuat ulang (umur 20:00:03) dalam 6.6 dtk`.
- **Jika muncul `GalatVerifikasi`:** run sengaja berhenti karena ada pengecekan
  kebenaran yang gagal (mis. transaksi bocor). Percobaan itu TIDAK dicatat. Simpan
  pesan galatnya untuk diperiksa sebelum melanjutkan.
- Jangan jalankan dua runner sekaligus (ketiganya memakai port dan folder yang
  sama).

---

## 9. Membaca hasil CSV

Kolom `results/hasil_percobaan.csv`:

| Kolom | Arti |
|---|---|
| `p` | porsi hashrate penyerang (teks 2 desimal, mis. `0.05`) |
| `k` | konfirmasi yang ditunggu merchant |
| `i` | nomor percobaan dalam kombinasi (0–999) |
| `berhasil` | `True` jika double spending berhasil (diverifikasi di node merchant) |
| `m` | blok yang ditambang penyerang saat hasil sudah pasti |
| `n` | blok yang ditambang honest saat hasil sudah pasti |
| `alasan_berhenti` | `menang` atau `berhenti_awal` (lihat T5) |
| `seed` | seed percobaan; menjalankan ulang seed yang sama memberi hasil sama |

Tingkat keberhasilan satu kombinasi = jumlah `berhasil = True` ÷ 1.000 × 100%.
Untuk sel dengan peluang sangat kecil, hasil 0 dari 1.000 adalah batas resolusi,
bukan bukti peluang nol.

---

## 10. Batasan (wajib ditulis di laporan)

- Regtest adalah lingkungan terkendali; hasil tidak merepresentasikan mainnet
  (hashrate global, latensi, mempool, fee).
- Hashrate penyerang diemulasikan lewat undian probabilistik, bukan daya tambang
  nyata. Eksperimen ini memverifikasi apakah implementasi Bitcoin Core nyata
  sesuai model pada kondisi ideal, bukan mengukur risiko mainnet.
- Penyerang tidak melakukan pre-mine; seri dihitung gagal.
- Aturan berhenti 20 blok (Rosenfeld 2014) memotong perlombaan; lihat T5 untuk
  dampaknya pada perbandingan dengan Nakamoto.
- Baseline didanai (fixture awal tiap percobaan) dibuat ulang tiap ≤ 20 jam,
  karena Bitcoin Core dengan setting default memperlakukan node yang ujung
  rantainya berumur > 24 jam sebagai *Initial Block Download* dan berhenti
  meminta rantai penyerang setelah disambung kembali (T10). Konfigurasi node
  tidak diubah; hasil percobaan tidak bergantung pada baseline mana yang dipakai.
- Di mesin Windows dengan rentang port dinamis tidak standar (ROG: 1024–65535),
  blok port proyek 18500–18699 dikecualikan dari port asal otomatis Windows, dan
  `tunggu_rpc_siap` mencoba ulang saat menerima `HTTPException`. Tujuannya
  mencegah koneksi RPC tersambung ke dirinya sendiri (TCP self-connect, T11).
  Ini perubahan lingkungan uji dan penanganan galat koneksi, bukan perubahan
  Bitcoin Core atau konfigurasinya; hasil percobaan tidak terpengaruh.
- Di Windows, folder data node dikecualikan dari pemindaian antivirus dan
  pengindeks berkas, dan runner mengulang reset ke baseline (maks. 3 kali) bila
  bitcoind gagal membuka database blok karena file salinan baseline dikunci
  proses lain (T12). Kegagalan terjadi sebelum percobaan dimulai dan undian
  ditentukan seed, sehingga hasil percobaan tidak terpengaruh.
- Transaksi tidak disebarkan antar-node lewat relay biasa: tx A dikirim langsung
  ke merchant dan honest (relay Bitcoin Core sengaja diberi jeda acak). Latensi
  jaringan memang di luar lingkup.

---

## 11. Langkah berikutnya

- **Tahap 3 (sisa):** run penuh 63.000 percobaan di ROG → `results/hasil_percobaan.csv`.
- **Tahap 4 — `src/analysis.py`:** hitung persentase keberhasilan per (p, k),
  tabel, grafik garis (X = k, satu garis per p), dan kurva Nakamoto (z = k)
  pada grafik yang sama. Butuh pandas dan matplotlib.
- **Tahap 5:** rekomendasi konfirmasi minimum per p, temuan sisi merchant (T6),
  batasan, dan pembaruan dokumen ini sesuai kode final.
