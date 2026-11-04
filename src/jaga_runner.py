"""
jaga_runner.py — Menjalankan runner.py dan menyalakannya lagi bila crash.

Run penuh berjalan berhari-hari tanpa ditunggui. Galat lingkungan yang jarang
(lihat brief/Dokumentasi.md temuan T10–T13) menghentikan runner, padahal run
bisa langsung dilanjutkan karena runner bersifat resumable. Program ini:
- menjalankan runner.py dengan argumen yang sama;
- bila runner crash: menyalin node_data dan pesan galat ke
  ..\\bukti_crash_<waktu> (node sudah dimatikan runner), menunggu sebentar,
  lalu menjalankan runner lagi;
- TIDAK menyalakan ulang bila run selesai, bila Ctrl+C ditekan, bila muncul
  GalatVerifikasi (harus diperiksa manusia dulu), atau bila beberapa sesi
  berturut-turut crash tanpa menambah satu baris pun.

Cara pakai (dari root proyek), argumen sama dengan runner.py:
    python src/jaga_runner.py
"""

import shutil
import subprocess
import sys
import time

import network
import runner

# Jeda sebelum runner dinyalakan lagi setelah crash.
JEDA_SEBELUM_ULANG_DETIK = 30

# Berhenti bila sekian sesi berturut-turut crash tanpa menambah baris CSV.
BATAS_SESI_TANPA_KEMAJUAN = 3


def cetak(pesan):
    """Cetak pesan penjaga dengan cap waktu, mengikuti format heartbeat."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [jaga] {pesan}", flush=True)


def jumlah_baris(file_csv):
    """Hitung baris file CSV (0 bila belum ada). Hanya membaca."""
    if not file_csv.exists():
        return 0
    with open(file_csv, encoding="utf-8") as berkas:
        return sum(1 for _ in berkas)


def simpan_bukti(teks_galat):
    """
    Salin node_data dan pesan galat ke ..\\bukti_crash_<waktu>.
    Output: folder bukti.
    """
    folder_bukti = network.folder_bukti_baru()
    folder_bukti.mkdir(parents=True)
    (folder_bukti / "galat.txt").write_text(teks_galat, encoding="utf-8")
    if network.FOLDER_DATA_NODE.exists():
        try:
            shutil.copytree(
                network.FOLDER_DATA_NODE, folder_bukti / "node_data"
            )
        except shutil.Error as galat:
            # Sebagian file gagal disalin (mis. masih dikunci); sisanya tetap
            # tersimpan.
            cetak(f"sebagian node_data gagal disalin: {len(galat.args[0])} file")
    return folder_bukti


def jalankan_satu_sesi(argumen_runner):
    """
    Jalankan runner.py sekali sampai keluar.

    Output stdout runner langsung tampil di terminal. Output stderr (tempat
    traceback) ditampilkan juga, sekaligus disimpan untuk bukti.
    Output: (kode keluar, teks stderr).
    """
    proses = subprocess.Popen(
        [sys.executable, "-u", str(network.FOLDER_PROYEK / "src" / "runner.py"),
         *argumen_runner],
        cwd=network.FOLDER_PROYEK,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    baris_stderr = []
    try:
        for baris in proses.stderr:
            sys.stderr.write(baris)
            baris_stderr.append(baris)
        proses.wait()
    except KeyboardInterrupt:
        # Ctrl+C juga diterima runner; tunggu runner mematikan node dengan
        # rapi, lalu teruskan Ctrl+C agar penjaga ikut berhenti. stderr tetap
        # dibaca sampai habis: bila tidak, pipe penuh oleh traceback runner,
        # runner macet menulis, dan penjaga macet menunggunya.
        for baris in proses.stderr:
            sys.stderr.write(baris)
        proses.wait()
        raise
    return proses.returncode, "".join(baris_stderr)


def jaga(argumen_runner, file_csv):
    """Loop penjaga: jalankan runner, nyalakan lagi bila crash."""
    sesi_tanpa_kemajuan = 0
    nomor_sesi = 0
    while True:
        nomor_sesi = nomor_sesi + 1
        baris_awal = jumlah_baris(file_csv)
        cetak(f"sesi {nomor_sesi} dimulai ({baris_awal} baris di CSV)")
        kode_keluar, teks_galat = jalankan_satu_sesi(argumen_runner)
        baris_akhir = jumlah_baris(file_csv)

        if kode_keluar == 0:
            cetak("runner selesai normal; penjaga berhenti")
            return
        if "KeyboardInterrupt" in teks_galat:
            cetak("runner dihentikan Ctrl+C; penjaga berhenti")
            return

        try:
            folder_bukti = simpan_bukti(teks_galat)
            cetak(f"runner crash (kode {kode_keluar}); bukti disimpan di "
                  f"{folder_bukti}")
        except Exception as galat_bukti:
            # Gagal menyimpan bukti tidak boleh menghentikan penjaga.
            cetak(f"runner crash (kode {kode_keluar}); bukti gagal disimpan: "
                  f"{galat_bukti!r}")
        if "GalatVerifikasi" in teks_galat:
            cetak("GalatVerifikasi: periksa dulu sebelum melanjutkan; "
                  "penjaga berhenti")
            sys.exit(1)

        if baris_akhir > baris_awal:
            sesi_tanpa_kemajuan = 0
        else:
            sesi_tanpa_kemajuan = sesi_tanpa_kemajuan + 1
        if sesi_tanpa_kemajuan >= BATAS_SESI_TANPA_KEMAJUAN:
            cetak(f"{sesi_tanpa_kemajuan} sesi berturut-turut crash tanpa "
                  f"baris baru; penjaga berhenti")
            sys.exit(1)

        cetak(f"menyalakan runner lagi dalam {JEDA_SEBELUM_ULANG_DETIK} dtk")
        time.sleep(JEDA_SEBELUM_ULANG_DETIK)


if __name__ == "__main__":
    # Lokasi CSV dibaca dengan pengurai argumen runner agar sama persis.
    argumen = runner.baca_argumen()
    try:
        jaga(sys.argv[1:], network.FOLDER_PROYEK / argumen.csv)
    except KeyboardInterrupt:
        cetak("dihentikan Ctrl+C")
