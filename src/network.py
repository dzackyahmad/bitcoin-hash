"""
network.py — Mengelola jaringan 3 node Bitcoin Core regtest.

Tiga node yang dipakai:
- merchant : penjual yang menerima pembayaran dari penyerang.
- honest   : penambang jujur yang menambang rantai publik.
- attacker : penyerang yang mencoba double spending.

File ini hanya berisi fungsi bantu jaringan (nyalakan, matikan, perintah RPC).
Logika serangan ada di trial.py.
"""

import base64
import http.client
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Lokasi file penting
# ---------------------------------------------------------------------------

# Folder root proyek (satu tingkat di atas folder src/).
FOLDER_PROYEK = Path(__file__).resolve().parent.parent

# Versi Bitcoin Core yang dipakai. Paket resminya diekstrak ke folder
# bitcoin-<versi>/ di root proyek (lihat brief/Dokumentasi.md).
VERSI_BITCOIN_CORE = "32.1"

# Program bitcoind (node Bitcoin Core). Di Windows namanya bitcoind.exe,
# di macOS/Linux bitcoind.
if os.name == "nt":
    NAMA_PROGRAM_BITCOIND = "bitcoind.exe"
else:
    NAMA_PROGRAM_BITCOIND = "bitcoind"
PROGRAM_BITCOIND = (
    FOLDER_PROYEK / f"bitcoin-{VERSI_BITCOIN_CORE}" / "bin"
    / NAMA_PROGRAM_BITCOIND
)

# Proses bitcoind yang dinyalakan oleh skrip ini, per nama node. Disimpan
# agar proses bisa "dipungut" (ditunggu selesai) setelah dimatikan.
PROSES_NODE = {}

# Folder file konfigurasi tiap node
# (merchant.conf, honest.conf, attacker.conf).
FOLDER_KONFIGURASI = FOLDER_PROYEK / "config"

# Folder tempat tiap node menyimpan datanya (blockchain, mempool, wallet).
# Isinya dibuat otomatis oleh bitcoind dan boleh dihapus kapan saja.
FOLDER_DATA_NODE = FOLDER_PROYEK / "node_data"

# Salinan node_data pada kondisi "baseline didanai" (dana penyerang sudah
# matang). Tiap percobaan dimulai dari salinan ini agar tidak perlu menambang
# ulang 101 blok maturasi.
FOLDER_BASELINE = FOLDER_PROYEK / "node_data_baseline"

# Nama ketiga node, dan port RPC masing-masing.
# Port ini HARUS sama dengan nilai rpcport di file config/<nama>.conf.
PORT_RPC_NODE = {
    "merchant": 18501,
    "honest": 18502,
    "attacker": 18503,
}

# Port P2P tiap node, yaitu port yang dipakai antar-node untuk bertukar blok
# dan transaksi. HARUS sama dengan nilai port di file config/<nama>.conf.
PORT_P2P_NODE = {
    "merchant": 18601,
    "honest": 18602,
    "attacker": 18603,
}

# Nama pengguna & kata sandi RPC (sama dengan rpcuser/rpcpassword di config).
RPC_USER = "jkkd"
RPC_PASSWORD = "jkkd"


# ---------------------------------------------------------------------------
# Perintah RPC (cara Python "berbicara" dengan node)
# ---------------------------------------------------------------------------

class GalatRPC(Exception):
    """Galat yang dikembalikan node saat sebuah perintah RPC gagal."""


def panggil_rpc(nama_node, perintah, *parameter):
    """
    Kirim satu perintah RPC ke node, lalu kembalikan hasilnya.

    Input : nama_node (mis. "merchant"), perintah (mis. "getblockcount"),
            dan parameter perintah bila ada.
    Output: nilai "result" dari jawaban node. Melempar GalatRPC jika node
            menjawab dengan pesan galat.
    """
    alamat = f"http://127.0.0.1:{PORT_RPC_NODE[nama_node]}/"

    # Isi permintaan dalam format JSON-RPC, format standar Bitcoin Core.
    # default=str: nominal BTC bertipe Decimal dikirim sebagai teks
    # (mis. "39.9999"), format yang juga diterima Bitcoin Core.
    isi_permintaan = json.dumps({
        "jsonrpc": "1.0",
        "id": "jkkd",
        "method": perintah,
        "params": list(parameter),
    }, default=str).encode()

    # Header otorisasi: nama pengguna & kata sandi RPC.
    teks_kredensial = f"{RPC_USER}:{RPC_PASSWORD}"
    kredensial = base64.b64encode(teks_kredensial.encode()).decode()
    permintaan = urllib.request.Request(alamat, data=isi_permintaan)
    permintaan.add_header("Authorization", f"Basic {kredensial}")
    permintaan.add_header("Content-Type", "application/json")

    # parse_float=Decimal: angka pecahan (nominal BTC) dibaca sebagai Decimal,
    # bukan float, agar nilai seperti 39.9999 tidak meleset karena pembulatan.
    try:
        with urllib.request.urlopen(permintaan, timeout=60) as jawaban:
            isi_jawaban = json.loads(jawaban.read(), parse_float=Decimal)
    except urllib.error.HTTPError as galat_http:
        # Bitcoin Core mengirim galat RPC dengan kode HTTP 4xx/5xx,
        # tetapi isinya tetap JSON yang menjelaskan galatnya.
        isi_jawaban = json.loads(galat_http.read(), parse_float=Decimal)

    if isi_jawaban.get("error"):
        raise GalatRPC(f"[{nama_node}] {perintah}: {isi_jawaban['error']}")
    return isi_jawaban["result"]


# ---------------------------------------------------------------------------
# Menyalakan & mematikan node
# ---------------------------------------------------------------------------

def folder_data(nama_node):
    """Kembalikan folder data milik satu node, mis. node_data/merchant."""
    return FOLDER_DATA_NODE / nama_node


def node_sedang_jalan(nama_node):
    """
    Cek apakah node sedang berjalan.

    Selama berjalan, bitcoind menyimpan file bitcoind.pid di folder datanya
    dan menghapusnya setelah benar-benar berhenti. Output: True/False.
    """
    file_pid = folder_data(nama_node) / "regtest" / "bitcoind.pid"
    return file_pid.exists()


def tunggu_rpc_siap(nama_node, batas_detik=30):
    """
    Tunggu sampai node siap menerima perintah RPC.

    Setelah dinyalakan, node butuh beberapa detik untuk memuat data.
    Output: tidak ada; melempar TimeoutError jika node tidak siap tepat waktu.
    """
    batas_waktu = time.time() + batas_detik
    while time.time() < batas_waktu:
        try:
            panggil_rpc(nama_node, "getblockchaininfo")
            return
        except (OSError, GalatRPC, http.client.HTTPException):
            # Node belum siap (port belum terbuka / masih memuat). Coba lagi.
            # HTTPException ikut ditangkap: di Windows, koneksi ke port yang
            # belum didengarkan bisa tersambung ke dirinya sendiri (TCP
            # self-connect) dan menghasilkan BadStatusLine. Lihat
            # brief/Dokumentasi.md temuan T11.
            time.sleep(0.2)
    raise TimeoutError(
        f"Node {nama_node} tidak siap dalam {batas_detik} detik"
    )


def opsi_kelompok_proses_terpisah():
    """
    Opsi agar bitcoind berjalan di kelompok proses tersendiri.

    Tanpa ini, menekan Ctrl+C di terminal juga mengirim sinyal ke ketiga
    bitcoind sehingga node mati sendiri di tengah jalan. Dengan opsi ini,
    Ctrl+C hanya diterima Python, lalu Python mematikan node dengan rapi.
    Output: dict argumen tambahan untuk subprocess.Popen.
    """
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def nyalakan_node(nama_node):
    """
    Nyalakan satu node bitcoind di mode regtest dan tunggu sampai siap.

    Input : nama_node. Output: tidak ada.
    """
    folder_data(nama_node).mkdir(parents=True, exist_ok=True)
    file_konfigurasi = FOLDER_KONFIGURASI / f"{nama_node}.conf"

    if not PROGRAM_BITCOIND.exists():
        raise FileNotFoundError(
            f"bitcoind tidak ditemukan: {PROGRAM_BITCOIND}"
        )

    # -regtest ditulis eksplisit (selain regtest=1 di config) sebagai pengaman
    # ganda agar node tidak pernah berjalan di jaringan Bitcoin sungguhan.
    # Node dijalankan di latar belakang lewat Popen (bukan opsi -daemon,
    # karena -daemon tidak tersedia di Windows).
    PROSES_NODE[nama_node] = subprocess.Popen(
        [
            str(PROGRAM_BITCOIND),
            "-regtest",
            f"-conf={file_konfigurasi}",
            f"-datadir={folder_data(nama_node)}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **opsi_kelompok_proses_terpisah(),
    )
    tunggu_rpc_siap(nama_node)


def matikan_node(nama_node, batas_detik=30):
    """
    Matikan satu node dengan rapi lewat perintah RPC "stop", lalu tunggu
    sampai prosesnya benar-benar berhenti.

    Jika RPC tidak bisa dihubungi (mis. node sedang menyala, atau sudah
    mendapat sinyal berhenti), proses dihentikan lewat sinyal terminate.
    Input : nama_node. Output: tidak ada.
    """
    proses = PROSES_NODE.get(nama_node)
    if not node_sedang_jalan(nama_node) and proses is None:
        return

    if node_sedang_jalan(nama_node):
        try:
            panggil_rpc(nama_node, "stop")
        except (OSError, GalatRPC):
            if proses is not None and proses.poll() is None:
                proses.terminate()

    batas_waktu = time.time() + batas_detik
    while node_sedang_jalan(nama_node):
        # Proses sudah keluar tetapi file pid masih ada (proses dihentikan
        # paksa): file pid itu basi, hapus saja.
        if proses is not None and proses.poll() is not None:
            file_pid = folder_data(nama_node) / "regtest" / "bitcoind.pid"
            file_pid.unlink(missing_ok=True)
            break
        if time.time() > batas_waktu:
            if proses is not None:
                proses.kill()
                continue
            raise TimeoutError(
                f"Node {nama_node} tidak berhenti dalam {batas_detik} detik"
            )
        time.sleep(0.2)

    # Pungut proses yang sudah berhenti. Tanpa ini, di macOS/Linux proses
    # yang mati tetap tercatat sebagai "zombie" dan bisa menumpuk ribuan.
    # (Node yang dinyalakan oleh proses Python lain tidak punya catatan
    # di PROSES_NODE; cukup ditunggu lewat file pid seperti di atas.)
    PROSES_NODE.pop(nama_node, None)
    if proses is not None:
        proses.wait(timeout=batas_detik)


def nyalakan_semua_node():
    """Nyalakan ketiga node (merchant, honest, attacker)."""
    for nama_node in PORT_RPC_NODE:
        nyalakan_node(nama_node)


def matikan_semua_node():
    """
    Matikan ketiga node. Semua node tetap dicoba dimatikan walaupun salah
    satunya gagal; galat pertama baru dilempar setelah semua dicoba.
    """
    galat_pertama = None
    for nama_node in PORT_RPC_NODE:
        try:
            matikan_node(nama_node)
        except Exception as galat:
            if galat_pertama is None:
                galat_pertama = galat
    if galat_pertama is not None:
        raise galat_pertama


# ---------------------------------------------------------------------------
# Menyambung & memutus node (membentuk dan memecah jaringan)
# ---------------------------------------------------------------------------

def jumlah_peer(nama_node):
    """Kembalikan jumlah peer (node lain) yang tersambung ke node ini."""
    daftar_peer = panggil_rpc(nama_node, "getpeerinfo")
    return len(daftar_peer)


def tunggu_jumlah_peer(nama_node, jumlah_diharapkan, batas_detik=10):
    """
    Tunggu sampai node memiliki tepat sejumlah peer yang diharapkan.

    Sambung/putus tidak terjadi seketika, jadi kita cek berulang.
    Output: tidak ada; melempar TimeoutError jika jumlah peer tidak tercapai.
    """
    batas_waktu = time.time() + batas_detik
    while time.time() < batas_waktu:
        if jumlah_peer(nama_node) == jumlah_diharapkan:
            return
        time.sleep(0.1)
    raise TimeoutError(
        f"Node {nama_node} punya {jumlah_peer(nama_node)} peer, "
        f"diharapkan {jumlah_diharapkan}"
    )


def sambungkan_dua_node(node_asal, node_tujuan):
    """
    Sambungkan node_asal ke node_tujuan lewat perintah addnode.

    Mode "onetry" berarti node mencoba tersambung sekali saja dan TIDAK
    menyambung ulang otomatis bila diputus. Ini penting agar penyerang tidak
    tiba-tiba tersambung kembali saat sedang menambang rantai rahasia.
    """
    alamat_tujuan = f"127.0.0.1:{PORT_P2P_NODE[node_tujuan]}"
    panggil_rpc(node_asal, "addnode", alamat_tujuan, "onetry")


def sambungkan_semua_node():
    """
    Bentuk jaringan penuh: setiap node tersambung ke dua node lainnya
    (merchant–honest, merchant–attacker, honest–attacker), lalu tunggu
    sampai tiap node melihat 2 peer.
    """
    sambungkan_dua_node("merchant", "honest")
    sambungkan_dua_node("merchant", "attacker")
    sambungkan_dua_node("honest", "attacker")
    for nama_node in PORT_RPC_NODE:
        tunggu_jumlah_peer(nama_node, 2)


def putuskan_penyerang():
    """
    Isolasi node penyerang dari jaringan.

    Dipakai "setnetworkactive false": node penyerang memutus SEMUA sambungan
    P2P dan menolak sambungan baru. Akibatnya blok dan transaksi tidak bisa
    keluar-masuk node penyerang, sehingga rantai rahasianya benar-benar
    tersembunyi. Merchant dan honest tetap saling tersambung.
    """
    panggil_rpc("attacker", "setnetworkactive", False)
    tunggu_jumlah_peer("attacker", 0)
    tunggu_jumlah_peer("merchant", 1)
    tunggu_jumlah_peer("honest", 1)


def sambungkan_kembali_penyerang():
    """
    Sambungkan kembali node penyerang ke merchant dan honest.

    Jaringan P2P penyerang diaktifkan lagi, lalu penyerang menyambung ke
    kedua node lain. Setelah ini tiap node kembali melihat 2 peer.
    """
    panggil_rpc("attacker", "setnetworkactive", True)
    sambungkan_dua_node("attacker", "merchant")
    sambungkan_dua_node("attacker", "honest")
    for nama_node in PORT_RPC_NODE:
        tunggu_jumlah_peer(nama_node, 2)


# ---------------------------------------------------------------------------
# Sinkronisasi rantai blok
# ---------------------------------------------------------------------------

def tunggu_sinkron(daftar_node, batas_detik=30):
    """
    Tunggu sampai semua node di daftar_node memakai rantai yang sama.

    Yang dibandingkan adalah hash blok teratas (ujung rantai), bukan sekadar
    jumlah blok: dua rantai yang bercabang (fork) bisa sama panjang tetapi
    isinya berbeda. Output: hash blok teratas yang disepakati semua node;
    melempar TimeoutError jika node belum sepakat tepat waktu.
    """
    batas_waktu = time.time() + batas_detik
    while time.time() < batas_waktu:
        hash_teratas = set()
        for nama_node in daftar_node:
            hash_teratas.add(panggil_rpc(nama_node, "getbestblockhash"))
        if len(hash_teratas) == 1:
            return hash_teratas.pop()
        time.sleep(0.1)
    raise TimeoutError(
        f"Node {daftar_node} tidak sinkron dalam {batas_detik} detik"
    )


# ---------------------------------------------------------------------------
# Reset jaringan ke kondisi awal
# ---------------------------------------------------------------------------

def hapus_semua_data_node():
    """
    Hapus folder node_data beserta seluruh isinya (blockchain, mempool,
    wallet ketiga node). Hanya boleh dipanggil saat semua node mati.
    """
    for nama_node in PORT_RPC_NODE:
        if node_sedang_jalan(nama_node):
            raise RuntimeError(f"Node {nama_node} masih jalan; matikan dulu")

    # Pengaman: pastikan yang dihapus memang folder node_data milik proyek.
    if FOLDER_DATA_NODE.name != "node_data":
        raise RuntimeError(f"Folder tak terduga: {FOLDER_DATA_NODE}")
    if FOLDER_DATA_NODE.exists():
        shutil.rmtree(FOLDER_DATA_NODE)


def reset_bersih_total():
    """
    Kembalikan jaringan ke kondisi benar-benar kosong: matikan ketiga node,
    hapus semua datanya, nyalakan lagi, lalu sambungkan.

    Hasilnya: rantai hanya berisi blok genesis (tinggi 0), mempool kosong,
    dan belum ada wallet. Mode ini lambat jika diikuti penambangan ulang
    101 blok maturasi, jadi tidak dipakai di tiap percobaan Tahap 3.
    """
    matikan_semua_node()
    hapus_semua_data_node()
    nyalakan_semua_node()
    sambungkan_semua_node()


def simpan_baseline():
    """
    Simpan kondisi jaringan saat ini sebagai baseline: matikan ketiga node
    (agar data tersimpan rapi ke disk), lalu salin node_data ke
    node_data_baseline. Node dibiarkan mati setelahnya.
    """
    matikan_semua_node()
    if FOLDER_BASELINE.name != "node_data_baseline":
        raise RuntimeError(f"Folder tak terduga: {FOLDER_BASELINE}")
    if FOLDER_BASELINE.exists():
        shutil.rmtree(FOLDER_BASELINE)
    shutil.copytree(FOLDER_DATA_NODE, FOLDER_BASELINE)


def reset_ke_baseline():
    """
    Kembalikan jaringan ke kondisi baseline didanai: matikan ketiga node,
    ganti node_data dengan salinan baseline, nyalakan, lalu sambungkan.

    Karena seluruh folder data diganti, rantai, mempool, dan wallet
    ketiga node kembali persis seperti saat baseline disimpan.
    """
    if not FOLDER_BASELINE.exists():
        raise RuntimeError("Baseline belum dibuat; jalankan pembuatan dulu")
    matikan_semua_node()
    hapus_semua_data_node()
    shutil.copytree(FOLDER_BASELINE, FOLDER_DATA_NODE)
    nyalakan_semua_node()
    sambungkan_semua_node()


def reset_jaringan(mode="bersih_total"):
    """
    Reset jaringan sesuai mode yang dipilih.

    Mode yang tersedia:
    - "bersih_total"     : hapus semua data (lihat reset_bersih_total).
    - "baseline_didanai" : kembali ke kondisi saat dana penyerang sudah
                           matang, tanpa menambang ulang 101 blok
                           (lihat reset_ke_baseline).
    """
    if mode == "bersih_total":
        reset_bersih_total()
    elif mode == "baseline_didanai":
        reset_ke_baseline()
    else:
        raise ValueError(f"Mode reset tidak dikenal: {mode}")
