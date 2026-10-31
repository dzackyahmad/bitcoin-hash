"""
runner.py — Menjalankan seluruh percobaan dan menyimpan hasilnya ke CSV.

Grid percobaan: p (9 nilai) x k (7 nilai) x N = 1.000 percobaan
= 63.000 percobaan. Tiap percobaan memanggil trial.jalankan_satu_percobaan.

Sifat penting:
- CSV ditulis INKREMENTAL: satu baris langsung ditambahkan setiap kali
  satu percobaan selesai, sehingga hasil tidak hilang bila run berhenti.
- RESUMABLE: saat mulai, CSV yang sudah ada dibaca dan percobaan yang
  sudah tercatat dilewati. Cukup jalankan ulang perintah yang sama.
- Seed per percobaan berbentuk "2026|p=0.05|k=0|i=0", sehingga hasil
  dapat diulang persis di mesin mana pun.

Cara pakai (dari root proyek):
    python src/runner.py                      # run penuh 63.000 percobaan
    python src/runner.py --p 0.05 0.45 --k 0 3 --n 20 \
        --csv results/uji_kecil.csv           # uji kecil
"""

import argparse
import csv
import time

import network
import trial

# ---------------------------------------------------------------------------
# Parameter terkunci (lihat brief/plan_eksekusi.md bagian 2)
# ---------------------------------------------------------------------------

# Seed utama: dasar semua seed percobaan.
SEED_UTAMA = 2026

# Porsi hashrate penyerang p: 0,05 sampai 0,45, loncatan 0,05.
DAFTAR_P = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]

# Jumlah konfirmasi k yang ditunggu merchant: 0 sampai 6.
DAFTAR_K = [0, 1, 2, 3, 4, 5, 6]

# Jumlah percobaan per kombinasi (p, k).
JUMLAH_PERCOBAAN_PER_KOMBINASI = 1000

# File CSV hasil run penuh.
FILE_CSV_UTAMA = network.FOLDER_PROYEK / "results" / "hasil_percobaan.csv"

# Urutan kolom CSV.
KOLOM_CSV = [
    "p", "k", "i", "berhasil", "m", "n", "alasan_berhenti", "seed",
]

# Cetak progres setiap sekian percobaan.
CETAK_PROGRES_SETIAP = 10

# Baseline didanai dibuat ulang di awal tiap sesi dan setiap 20 jam.
# Mengapa: blok di baseline memakai waktu saat baseline dibuat. Jika umurnya
# lewat 24 jam, Bitcoin Core (setting default) menganggap node sedang
# "Initial Block Download" dan hanya meminta header dari satu peer, sehingga
# setelah penyerang disambung kembali, rantainya bisa tidak diminta dan node
# tidak sinkron (TimeoutError). 20 jam memberi jarak aman dari batas 24 jam.
# Lihat brief/Dokumentasi.md temuan T10.
BUAT_ULANG_BASELINE_SETIAP_DETIK = 20 * 3600


# ---------------------------------------------------------------------------
# Seed & kunci percobaan
# ---------------------------------------------------------------------------

def teks_p(p):
    """Tulis p sebagai teks 2 desimal (mis. 0.05) agar konsisten di CSV."""
    return f"{p:.2f}"


def buat_seed(p, k, nomor_percobaan):
    """Buat seed teks satu percobaan, mis. "2026|p=0.05|k=0|i=0"."""
    return f"{SEED_UTAMA}|p={teks_p(p)}|k={k}|i={nomor_percobaan}"


def kunci_percobaan(p_teks, k, nomor_percobaan):
    """
    Kunci unik satu percobaan untuk menandai yang sudah selesai.
    Semua bagian dijadikan teks agar perbandingan tidak terganggu
    pembulatan angka pecahan.
    """
    return (str(p_teks), str(k), str(nomor_percobaan))


# ---------------------------------------------------------------------------
# Membaca & menulis CSV
# ---------------------------------------------------------------------------

def baris_valid(baris):
    """
    Cek apakah satu baris CSV lengkap dan masuk akal. Baris terakhir bisa
    terpotong jika run berhenti tepat saat menulis. Output: True/False.
    """
    if baris is None or len(baris) != len(KOLOM_CSV):
        return False
    if any(nilai is None or nilai == "" for nilai in baris.values()):
        return False
    return baris["berhasil"] in ("True", "False")


def baca_percobaan_selesai(file_csv):
    """
    Baca CSV yang sudah ada dan kembalikan himpunan kunci percobaan yang
    sudah selesai. Jika ada baris rusak/terpotong, file ditulis ulang hanya
    dengan baris yang valid agar baris berikutnya tidak menyambung ke baris
    rusak. Jika file belum ada, buat file baru berisi judul kolom.
    Output: set berisi kunci (p, k, i).
    """
    if not file_csv.exists():
        file_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(file_csv, "w", newline="") as berkas:
            csv.writer(berkas).writerow(KOLOM_CSV)
        return set()

    baris_baik = []
    ada_baris_rusak = False
    with open(file_csv, newline="") as berkas:
        for baris in csv.DictReader(berkas):
            if baris_valid(baris):
                baris_baik.append(baris)
            else:
                ada_baris_rusak = True

    if ada_baris_rusak:
        print(f"Peringatan: baris rusak dibuang dari {file_csv.name}")
        with open(file_csv, "w", newline="") as berkas:
            penulis = csv.DictWriter(berkas, fieldnames=KOLOM_CSV)
            penulis.writeheader()
            penulis.writerows(baris_baik)

    percobaan_selesai = set()
    for baris in baris_baik:
        percobaan_selesai.add(
            kunci_percobaan(baris["p"], baris["k"], baris["i"])
        )
    return percobaan_selesai


def tambahkan_baris_csv(file_csv, p, k, nomor_percobaan, hasil):
    """
    Tambahkan hasil satu percobaan sebagai satu baris di akhir CSV.
    File dibuka-tutup tiap baris agar data langsung tersimpan ke disk.
    """
    baris = [
        teks_p(p),
        k,
        nomor_percobaan,
        hasil["berhasil"],
        hasil["blok_penyerang"],
        hasil["blok_jujur"],
        hasil["alasan_berhenti"],
        hasil["seed"],
    ]
    with open(file_csv, "a", newline="") as berkas:
        csv.writer(berkas).writerow(baris)


# ---------------------------------------------------------------------------
# Progres
# ---------------------------------------------------------------------------

def format_durasi(detik):
    """Ubah jumlah detik menjadi teks jam:menit:detik, mis. 5:03:12."""
    detik = int(detik)
    jam = detik // 3600
    menit = (detik % 3600) // 60
    sisa_detik = detik % 60
    return f"{jam}:{menit:02d}:{sisa_detik:02d}"


def cetak_progres(jumlah_selesai, jumlah_total, dikerjakan_sesi_ini,
                  waktu_mulai_sesi, sel_terakhir, jumlah_per_kombinasi):
    """
    Cetak satu baris heartbeat: posisi global (selesai dari total), posisi
    di sel (p, k) yang sedang dikerjakan, laju percobaan per detik di sesi
    ini, dan perkiraan sisa waktu (ETA).

    sel_terakhir = (p, k, nomor_percobaan) dari percobaan terakhir yang
    selesai. Nomor percobaan mulai dari 0, jadi yang dicetak nomor + 1
    (jumlah percobaan sel itu yang sudah selesai).
    """
    lama_sesi = time.time() - waktu_mulai_sesi
    laju = dikerjakan_sesi_ini / lama_sesi
    sisa_percobaan = jumlah_total - jumlah_selesai
    perkiraan_sisa = sisa_percobaan / laju
    persen = 100 * jumlah_selesai / jumlah_total
    p, k, nomor_percobaan = sel_terakhir
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
        f"global {jumlah_selesai}/{jumlah_total} ({persen:.1f}%) | "
        f"sel ({teks_p(p)}, {k}) "
        f"{nomor_percobaan + 1}/{jumlah_per_kombinasi} | "
        f"laju {laju:.3f} trial/dtk | "
        f"ETA {format_durasi(perkiraan_sisa)}",
        flush=True,
    )


def buat_ulang_baseline(alasan):
    """
    Buat ulang baseline didanai dengan fungsi yang sudah ada
    (trial.buat_baseline_didanai), lalu cetak satu baris log.
    Input: alasan pembuatan ulang (teks untuk log).
    Output: waktu (time.time()) saat baseline selesai dibuat.
    """
    waktu_mulai = time.time()
    trial.buat_baseline_didanai()
    waktu_selesai = time.time()
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
        f"baseline didanai dibuat ulang ({alasan}) dalam "
        f"{waktu_selesai - waktu_mulai:.1f} dtk",
        flush=True,
    )
    return waktu_selesai


# ---------------------------------------------------------------------------
# Loop utama
# ---------------------------------------------------------------------------

def jalankan_semua_percobaan(daftar_p, daftar_k, jumlah_per_kombinasi,
                             file_csv):
    """
    Jalankan semua kombinasi p x k x N, lewati yang sudah ada di CSV.

    Jika baseline didanai belum ada (mis. pertama kali di mesin baru),
    baseline dibuat dulu. Jika sebuah percobaan gagal verifikasi
    (GalatVerifikasi), run DIHENTIKAN dan percobaan itu tidak dicatat,
    karena hasilnya tidak bisa dipercaya.
    """
    percobaan_selesai = baca_percobaan_selesai(file_csv)
    jumlah_total = len(daftar_p) * len(daftar_k) * jumlah_per_kombinasi
    jumlah_selesai = 0
    for p in daftar_p:
        for k in daftar_k:
            for nomor_percobaan in range(jumlah_per_kombinasi):
                kunci = kunci_percobaan(teks_p(p), k, nomor_percobaan)
                if kunci in percobaan_selesai:
                    jumlah_selesai = jumlah_selesai + 1
    print(f"CSV: {file_csv}")
    print(f"Sudah selesai sebelumnya: {jumlah_selesai}/{jumlah_total}")

    # Selalu buat baseline baru di awal sesi, karena baseline dari sesi
    # sebelumnya bisa sudah berumur lebih dari 24 jam
    # (lihat BUAT_ULANG_BASELINE_SETIAP_DETIK).
    waktu_baseline_dibuat = buat_ulang_baseline("awal sesi")

    waktu_mulai_sesi = time.time()
    dikerjakan_sesi_ini = 0
    try:
        for p in daftar_p:
            for k in daftar_k:
                for nomor_percobaan in range(jumlah_per_kombinasi):
                    kunci = kunci_percobaan(teks_p(p), k, nomor_percobaan)
                    if kunci in percobaan_selesai:
                        continue

                    # Buat ulang baseline sebelum umurnya mendekati 24 jam.
                    umur_baseline = time.time() - waktu_baseline_dibuat
                    if umur_baseline >= BUAT_ULANG_BASELINE_SETIAP_DETIK:
                        waktu_baseline_dibuat = buat_ulang_baseline(
                            f"umur {format_durasi(umur_baseline)}"
                        )

                    seed = buat_seed(p, k, nomor_percobaan)
                    hasil = trial.jalankan_satu_percobaan(p, k, seed)
                    tambahkan_baris_csv(
                        file_csv, p, k, nomor_percobaan, hasil
                    )

                    jumlah_selesai = jumlah_selesai + 1
                    dikerjakan_sesi_ini = dikerjakan_sesi_ini + 1
                    # Ingat posisi percobaan terakhir untuk baris heartbeat.
                    sel_terakhir = (p, k, nomor_percobaan)
                    if dikerjakan_sesi_ini % CETAK_PROGRES_SETIAP == 0:
                        cetak_progres(
                            jumlah_selesai, jumlah_total,
                            dikerjakan_sesi_ini, waktu_mulai_sesi,
                            sel_terakhir, jumlah_per_kombinasi,
                        )
    finally:
        # Matikan node apa pun yang terjadi (selesai, galat, atau Ctrl+C).
        network.matikan_semua_node()

    if dikerjakan_sesi_ini > 0:
        cetak_progres(
            jumlah_selesai, jumlah_total, dikerjakan_sesi_ini,
            waktu_mulai_sesi, sel_terakhir, jumlah_per_kombinasi,
        )
    print("Selesai.")


def baca_argumen():
    """
    Baca argumen baris perintah. Tanpa argumen, dipakai parameter terkunci
    (run penuh). Argumen dipakai untuk uji kecil.
    """
    pengurai = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    pengurai.add_argument("--p", type=float, nargs="+", default=DAFTAR_P,
                          help="daftar nilai p")
    pengurai.add_argument("--k", type=int, nargs="+", default=DAFTAR_K,
                          help="daftar nilai k")
    pengurai.add_argument("--n", type=int,
                          default=JUMLAH_PERCOBAAN_PER_KOMBINASI,
                          help="jumlah percobaan per kombinasi")
    pengurai.add_argument("--csv", default=str(FILE_CSV_UTAMA),
                          help="lokasi file CSV hasil")
    return pengurai.parse_args()


if __name__ == "__main__":
    argumen = baca_argumen()
    jalankan_semua_percobaan(
        argumen.p, argumen.k, argumen.n,
        network.FOLDER_PROYEK / argumen.csv,
    )
