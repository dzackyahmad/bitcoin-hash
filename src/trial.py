"""
trial.py — Satu percobaan serangan double spending berbasis fork.

Isi file ini:
- Pembuatan baseline didanai (dijalankan SEKALI sebelum semua percobaan):
  penyerang punya koin matang yang siap dibelanjakan dua kali.
- Fungsi satu percobaan serangan (jalankan_satu_percobaan, Langkah 1-7).

Fungsi jaringan (nyalakan, sambung, putus, reset) ada di network.py.
"""

import random
import time
from decimal import Decimal

import network

# ---------------------------------------------------------------------------
# Konstanta pendanaan & transaksi
# ---------------------------------------------------------------------------

# Koin hasil tambang (coinbase) baru boleh dibelanjakan setelah ada 100 blok
# di atasnya. Aturan ini disebut "maturasi coinbase".
BLOK_MATURASI = 100

# Hadiah satu blok di regtest pada tinggi rendah: 50 BTC.
HADIAH_BLOK_BTC = 50

# Nominal yang dibayarkan penyerang ke merchant (tx A).
NOMINAL_BAYAR_BTC = Decimal("10")

# Biaya transaksi (fee) untuk penambang. Dibuat sama untuk tx A dan tx B.
# Fee = jumlah input dikurangi jumlah semua output.
FEE_BTC = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Fungsi bantu wallet & penambangan
# ---------------------------------------------------------------------------

def buat_wallet(nama_node):
    """
    Buat satu wallet bernama sama dengan node, mis. wallet "attacker" di
    node attacker. Wallet otomatis dimuat lagi saat node dinyalakan ulang.
    """
    # Urutan parameter createwallet: nama, tanpa_kunci_privat, kosong,
    # kata_sandi, hindari_pakai_ulang, descriptor, muat_saat_mulai.
    network.panggil_rpc(
        nama_node, "createwallet", nama_node, False, False, "", False,
        True, True,
    )


def alamat_baru(nama_node):
    """Minta satu alamat penerima baru dari wallet milik node."""
    return network.panggil_rpc(nama_node, "getnewaddress")


def tambang_banyak_blok(nama_node, jumlah_blok):
    """
    Tambang sejumlah blok di node ini, hadiahnya ke alamat baru milik node
    itu sendiri. Output: daftar hash blok yang ditambang.
    """
    alamat_penerima_hadiah = alamat_baru(nama_node)
    return network.panggil_rpc(
        nama_node, "generatetoaddress", jumlah_blok, alamat_penerima_hadiah
    )


# ---------------------------------------------------------------------------
# Baseline didanai (dibuat sekali)
# ---------------------------------------------------------------------------

def buat_baseline_didanai():
    """
    Siapkan kondisi awal semua percobaan, lalu simpan sebagai baseline.

    1. Reset total jaringan dan buat wallet di ketiga node.
    2. Penyerang menambang 1 blok: hadiahnya (50 BTC) adalah koin yang nanti
       dibelanjakan dua kali.
    3. Penambang jujur menambang 100 blok di atasnya agar koin itu matang.
    4. Simpan kondisi ini ke node_data_baseline.

    Output: tidak ada. Node dalam keadaan mati setelah fungsi selesai.
    """
    network.reset_jaringan("bersih_total")
    for nama_node in network.PORT_RPC_NODE:
        buat_wallet(nama_node)

    semua_node = list(network.PORT_RPC_NODE)

    # Tunggu sinkron setelah blok penyerang: jika honest langsung menambang
    # sebelum menerima blok itu, honest membangun rantai sendiri dari
    # genesis dan blok penyerang terbuang (fork yang tidak disengaja).
    tambang_banyak_blok("attacker", 1)
    network.tunggu_sinkron(semua_node)
    tambang_banyak_blok("honest", BLOK_MATURASI)
    network.tunggu_sinkron(semua_node)

    periksa_dana_penyerang_matang()
    network.simpan_baseline()


def periksa_dana_penyerang_matang():
    """
    Pastikan penyerang punya tepat satu koin matang senilai 50 BTC.

    Ini syarat percobaan: koin itulah yang dibelanjakan dua kali
    (ke merchant dan kembali ke penyerang). Melempar AssertionError
    jika tidak terpenuhi.
    """
    daftar_koin = network.panggil_rpc("attacker", "listunspent")
    assert len(daftar_koin) == 1, f"Koin penyerang: {daftar_koin}"
    assert daftar_koin[0]["amount"] == HADIAH_BLOK_BTC
    assert daftar_koin[0]["spendable"] is True


# ---------------------------------------------------------------------------
# Pembuatan dua transaksi yang saling bertentangan (double spend)
# ---------------------------------------------------------------------------

def ambil_koin_penyerang():
    """
    Ambil satu-satunya koin matang milik penyerang (UTXO = Unspent
    Transaction Output, yaitu koin yang belum dibelanjakan).

    Output: dict berisi "txid", "vout" (penunjuk koin), dan "amount".
    """
    periksa_dana_penyerang_matang()
    return network.panggil_rpc("attacker", "listunspent")[0]


def buat_transaksi_tertandatangani(koin, daftar_keluaran):
    """
    Buat satu transaksi mentah (raw transaction) yang membelanjakan koin,
    lalu tanda tangani dengan wallet penyerang.

    Transaksi mentah dipakai karena wallet biasa (sendtoaddress) menolak
    membelanjakan koin yang sama dua kali. Penandatanganan TIDAK
    menyiarkan transaksi dan TIDAK memasukkannya ke mempool: hasilnya
    hanya teks heksadesimal yang disimpan di Python.

    Input : koin (dari ambil_koin_penyerang), daftar_keluaran berupa dict
            {alamat: nominal_btc}.
    Output: transaksi bertanda tangan dalam bentuk heksadesimal.
    """
    daftar_masukan = [{"txid": koin["txid"], "vout": koin["vout"]}]
    transaksi_mentah = network.panggil_rpc(
        "attacker", "createrawtransaction", daftar_masukan, daftar_keluaran
    )
    hasil_tanda_tangan = network.panggil_rpc(
        "attacker", "signrawtransactionwithwallet", transaksi_mentah
    )
    assert hasil_tanda_tangan["complete"], hasil_tanda_tangan
    return hasil_tanda_tangan["hex"]


def buat_transaksi_pembayaran(koin, alamat_merchant, alamat_kembalian):
    """
    Buat tx A: penyerang membayar merchant.

    Koin 50 BTC dipecah menjadi 10 BTC untuk merchant dan sisanya
    (dikurangi fee) kembali ke penyerang sebagai uang kembalian.
    Output: heksadesimal tx A.
    """
    nominal_kembalian = koin["amount"] - NOMINAL_BAYAR_BTC - FEE_BTC
    daftar_keluaran = {
        alamat_merchant: NOMINAL_BAYAR_BTC,
        alamat_kembalian: nominal_kembalian,
    }
    return buat_transaksi_tertandatangani(koin, daftar_keluaran)


def buat_transaksi_tandingan(koin, alamat_penyerang):
    """
    Buat tx B: koin yang SAMA dikirim seluruhnya kembali ke penyerang.

    tx B memakai input yang sama dengan tx A, sehingga keduanya tidak
    mungkin sama-sama sah di satu rantai. Inilah inti double spending.
    Output: heksadesimal tx B.
    """
    daftar_keluaran = {alamat_penyerang: koin["amount"] - FEE_BTC}
    return buat_transaksi_tertandatangani(koin, daftar_keluaran)


# ---------------------------------------------------------------------------
# Pengecekan kebenaran (anti-bocor)
# ---------------------------------------------------------------------------

class GalatVerifikasi(Exception):
    """
    Galat saat pengecekan kebenaran gagal, mis. transaksi bocor ke sisi
    yang salah. Percobaan DIHENTIKAN, bukan dicatat sebagai serangan gagal,
    karena hasilnya tidak bisa dipercaya.
    """


def pastikan(kondisi, pesan):
    """Lempar GalatVerifikasi berisi pesan jika kondisi tidak terpenuhi."""
    if not kondisi:
        raise GalatVerifikasi(pesan)


def ada_di_mempool(nama_node, txid):
    """
    Cek apakah transaksi ada di mempool node. Mempool adalah ruang tunggu
    transaksi yang sudah diterima node tetapi belum masuk blok.
    Output: True/False.
    """
    try:
        network.panggil_rpc(nama_node, "getmempoolentry", txid)
        return True
    except network.GalatRPC:
        return False


# ---------------------------------------------------------------------------
# Fase pembuka: siapkan double spend, putus penyerang, siarkan pembayaran
# ---------------------------------------------------------------------------

def siapkan_double_spend():
    """
    Buat tx A (bayar merchant) dan tx B (tandingan) dari koin yang sama.
    Keduanya hanya disimpan di Python; belum ada yang disiarkan.

    Output: dict berisi heksadesimal dan txid kedua transaksi.
    """
    koin = ambil_koin_penyerang()
    hex_tx_a = buat_transaksi_pembayaran(
        koin, alamat_baru("merchant"), alamat_baru("attacker")
    )
    hex_tx_b = buat_transaksi_tandingan(koin, alamat_baru("attacker"))

    txid_tx_a = network.panggil_rpc(
        "attacker", "decoderawtransaction", hex_tx_a
    )["txid"]
    txid_tx_b = network.panggil_rpc(
        "attacker", "decoderawtransaction", hex_tx_b
    )["txid"]
    return {
        "hex_tx_a": hex_tx_a,
        "txid_tx_a": txid_tx_a,
        "hex_tx_b": hex_tx_b,
        "txid_tx_b": txid_tx_b,
    }


def siarkan_pembayaran(hex_tx_a):
    """
    Kirim tx A langsung ke merchant dan penambang jujur.

    Dikirim ke keduanya sekaligus (bukan menunggu diteruskan antar-node)
    karena Bitcoin Core sengaja menunda penerusan transaksi beberapa detik
    secara acak; menunggu jeda itu memperlambat tiap percobaan.
    """
    network.panggil_rpc("merchant", "sendrawtransaction", hex_tx_a)
    network.panggil_rpc("honest", "sendrawtransaction", hex_tx_a)


def periksa_sebelum_menambang(data_percobaan):
    """
    Cek anti-bocor setelah fase pembuka, sebelum blok pertama ditambang.

    Syarat: penyerang terisolasi, tx A ada di mempool merchant & honest,
    mempool penyerang kosong, tx B tidak ada di mempool mana pun, dan
    ketiga node masih di titik fork (belum ada blok baru).
    Melempar GalatVerifikasi jika ada syarat yang tidak terpenuhi.
    """
    txid_tx_a = data_percobaan["txid_tx_a"]
    txid_tx_b = data_percobaan["txid_tx_b"]
    titik_fork = data_percobaan["titik_fork"]

    pastikan(
        network.jumlah_peer("attacker") == 0,
        "Penyerang masih tersambung ke jaringan",
    )
    for nama_node in ("merchant", "honest"):
        pastikan(
            ada_di_mempool(nama_node, txid_tx_a),
            f"tx A tidak ada di mempool {nama_node}",
        )

    ukuran_mempool_penyerang = network.panggil_rpc(
        "attacker", "getmempoolinfo"
    )["size"]
    pastikan(
        ukuran_mempool_penyerang == 0,
        f"Mempool penyerang tidak kosong ({ukuran_mempool_penyerang} tx)",
    )

    for nama_node in network.PORT_RPC_NODE:
        pastikan(
            not ada_di_mempool(nama_node, txid_tx_b),
            f"tx B BOCOR ke mempool {nama_node}",
        )
        ujung_rantai = network.panggil_rpc(nama_node, "getbestblockhash")
        pastikan(
            ujung_rantai == titik_fork,
            f"Rantai {nama_node} sudah bergeser dari titik fork",
        )


def jalankan_fase_pembuka():
    """
    Fase pembuka satu percobaan (Langkah 2 rancangan):
    catat titik fork, siapkan tx A & tx B, putus penyerang, siarkan tx A,
    lalu jalankan cek anti-bocor.

    Output: dict data percobaan (titik fork, hex & txid tx A dan tx B).
    """
    # Titik fork = ujung rantai yang disepakati ketiga node saat ini.
    # Rantai publik dan rantai rahasia sama-sama bercabang dari sini.
    titik_fork = network.tunggu_sinkron(list(network.PORT_RPC_NODE))

    # tx A & tx B dibuat SEBELUM penyerang diputus, tetapi keduanya belum
    # disiarkan; menandatangani tidak mengirim apa pun ke jaringan.
    data_percobaan = siapkan_double_spend()
    data_percobaan["titik_fork"] = titik_fork
    data_percobaan["tinggi_fork"] = network.panggil_rpc(
        "merchant", "getblockcount"
    )

    # Penyerang diputus SEBELUM tx A disiarkan, sehingga tx A tidak pernah
    # sampai ke node penyerang.
    network.putuskan_penyerang()
    siarkan_pembayaran(data_percobaan["hex_tx_a"])

    periksa_sebelum_menambang(data_percobaan)
    return data_percobaan


# ---------------------------------------------------------------------------
# Undian paralel: perlombaan rantai rahasia vs rantai publik
# ---------------------------------------------------------------------------

# Penyerang menyerah jika sudah menambang 20 blok tanpa unggul
# (Rosenfeld 2014 §6).
BATAS_BLOK_PENYERANG = 20


class UrutanUndianPaksa:
    """
    Pengganti sumber acak untuk PENGUJIAN: hasil undian ditentukan lewat
    teks, mis. "PPJ" = blok penyerang, blok penyerang, blok jujur.
    Dipakai agar kasus menang/kalah/seri bisa diuji dengan pasti.
    """

    def __init__(self, urutan):
        self.sisa_urutan = list(urutan)

    def random(self):
        """Kembalikan 0.0 untuk "P" (pasti < p) atau 0.999999 untuk "J"."""
        huruf = self.sisa_urutan.pop(0)
        if huruf == "P":
            return 0.0
        return 0.999999


def tentukan_status(blok_penyerang, blok_jujur, k,
                    pakai_berhenti_awal=True):
    """
    Tentukan apakah perlombaan selesai setelah sebuah blok ditambang.

    Input : blok_penyerang (m), blok_jujur (n), k (konfirmasi yang
            ditunggu merchant).
    Output: "menang", "berhenti_awal", "menyerah", atau None (lanjut).

    Urutan cek penting: MENANG dicek lebih dulu.
    1. Menang: merchant sudah menganggap lunas (n >= k) DAN rantai rahasia
       lebih panjang (m > n). Sama panjang (seri) belum menang.
    2. Berhenti awal: jika n >= 20, penyerang mustahil menang (ia butuh
       m > n >= 20, padahal menyerah di m = 20), jadi hasil sudah pasti
       gagal tanpa perlu menambang lagi.
    3. Menyerah: penyerang sudah menambang >= 20 blok, tetapi rantainya
       tidak lebih panjang (m <= n).
    """
    if blok_jujur >= k and blok_penyerang > blok_jujur:
        return "menang"
    if pakai_berhenti_awal and blok_jujur >= BATAS_BLOK_PENYERANG:
        return "berhenti_awal"
    if (blok_penyerang >= BATAS_BLOK_PENYERANG
            and blok_penyerang <= blok_jujur):
        return "menyerah"
    return None


def tambang_satu_blok(nama_node, daftar_transaksi):
    """
    Tambang tepat satu blok di node ini dengan isi yang ditentukan sendiri
    (generateblock), hadiahnya ke alamat baru milik node itu.

    Input : daftar_transaksi berisi hex transaksi atau txid dari mempool;
            daftar kosong berarti blok tanpa transaksi (selain coinbase).
    Output: hash blok baru.
    """
    alamat_penerima_hadiah = alamat_baru(nama_node)
    hasil = network.panggil_rpc(
        nama_node, "generateblock", alamat_penerima_hadiah, daftar_transaksi
    )
    return hasil["hash"]


def pastikan_transaksi_di_blok(nama_node, hash_blok, txid):
    """Pastikan transaksi txid benar-benar termuat di blok hash_blok."""
    isi_blok = network.panggil_rpc(nama_node, "getblock", hash_blok)["tx"]
    pastikan(txid in isi_blok, f"{txid} tidak ada di blok {hash_blok}")


def catat_status_merchant_saat_lunas(data_percobaan, k):
    """
    Catat status tx A di wallet merchant tepat saat merchant menganggap
    lunas (Langkah 4), dan pastikan jumlah konfirmasinya memang k.
    Output: dict status tx A menurut wallet merchant (format sama dengan
    status sesudah reorg, lihat ambil_status_wallet_merchant).
    """
    txid_tx_a = data_percobaan["txid_tx_a"]
    status_merchant = ambil_status_wallet_merchant(txid_tx_a)
    pastikan(
        status_merchant["konfirmasi"] == k,
        f"Konfirmasi tx A di merchant {status_merchant['konfirmasi']}, "
        f"seharusnya {k}",
    )
    if k == 0:
        pastikan(
            ada_di_mempool("merchant", txid_tx_a),
            "k=0: tx A tidak ada di mempool merchant",
        )
    return status_merchant


def jalankan_undian_paralel(data_percobaan, p, k, sumber_acak,
                            pakai_berhenti_awal=True):
    """
    Jalankan perlombaan blok sejak tx A disiarkan (Langkah 3-5).

    Tiap langkah satu blok ditambang: dengan peluang p oleh penyerang
    (rantai rahasia), selain itu oleh penambang jujur (rantai publik).
    tx B masuk blok penyerang PERTAMA, tx A masuk blok jujur PERTAMA,
    kapan pun blok itu terjadi; blok lainnya kosong.

    Input : data_percobaan (dari fase pembuka), p, k, sumber_acak (objek
            dengan .random(), mis. random.Random atau UrutanUndianPaksa).
    Output: dict berisi m, n, status, urutan undian, hash blok pemuat
            tx A dan tx B, serta status merchant saat lunas.
    """
    blok_penyerang = 0
    blok_jujur = 0
    urutan_undian = ""
    hash_blok_tx_a = None
    hash_blok_tx_b = None
    hash_ujung_rahasia = data_percobaan["titik_fork"]
    status_merchant_saat_lunas = None

    # Langkah 4 (khusus k = 0): merchant langsung menganggap lunas saat
    # tx A masuk mempool, sebelum blok apa pun ditambang.
    if k == 0:
        status_merchant_saat_lunas = catat_status_merchant_saat_lunas(
            data_percobaan, k
        )

    status = None
    while status is None:
        # Langkah 3: undian siapa yang menemukan blok berikutnya.
        if sumber_acak.random() < p:
            # Blok rahasia penyerang (node penyerang sedang terisolasi).
            if blok_penyerang == 0:
                isi_blok = [data_percobaan["hex_tx_b"]]
            else:
                isi_blok = []
            hash_ujung_rahasia = tambang_satu_blok("attacker", isi_blok)
            if blok_penyerang == 0:
                hash_blok_tx_b = hash_ujung_rahasia
                pastikan_transaksi_di_blok(
                    "attacker", hash_blok_tx_b, data_percobaan["txid_tx_b"]
                )
            blok_penyerang = blok_penyerang + 1
            urutan_undian = urutan_undian + "P"
        else:
            # Blok publik penambang jujur.
            if blok_jujur == 0:
                isi_blok = [data_percobaan["txid_tx_a"]]
            else:
                isi_blok = []
            hash_blok_baru = tambang_satu_blok("honest", isi_blok)
            if blok_jujur == 0:
                hash_blok_tx_a = hash_blok_baru
                pastikan_transaksi_di_blok(
                    "honest", hash_blok_tx_a, data_percobaan["txid_tx_a"]
                )
            blok_jujur = blok_jujur + 1
            urutan_undian = urutan_undian + "J"

            # Merchant harus menerima blok ini dulu sebelum statusnya dicek.
            network.tunggu_sinkron(["merchant", "honest"])

            # Langkah 4: merchant menganggap lunas saat tx A punya k
            # konfirmasi (blok pemuat tx A = konfirmasi ke-1).
            if blok_jujur == k:
                status_merchant_saat_lunas = catat_status_merchant_saat_lunas(
                    data_percobaan, k
                )

        # Langkah 5: cek apakah perlombaan selesai (menang dicek dulu).
        status = tentukan_status(
            blok_penyerang, blok_jujur, k, pakai_berhenti_awal
        )

    return {
        "blok_penyerang": blok_penyerang,
        "blok_jujur": blok_jujur,
        "status": status,
        "menang_undian": status == "menang",
        "urutan_undian": urutan_undian,
        "hash_blok_tx_a": hash_blok_tx_a,
        "hash_blok_tx_b": hash_blok_tx_b,
        "hash_ujung_rahasia": hash_ujung_rahasia,
        "status_merchant_saat_lunas": status_merchant_saat_lunas,
    }


# ---------------------------------------------------------------------------
# Penyatuan jaringan & penentuan sukses (Langkah 6-7)
# ---------------------------------------------------------------------------

def blok_dikenal(nama_node, hash_blok):
    """Cek apakah node sudah pernah menerima blok ini. Output: True/False."""
    try:
        network.panggil_rpc(nama_node, "getblockheader", hash_blok)
        return True
    except network.GalatRPC:
        return False


def blok_di_rantai_aktif(nama_node, hash_blok):
    """
    Cek apakah blok termasuk rantai aktif (rantai utama) node ini.

    Bitcoin Core memberi nilai confirmations = -1 untuk blok yang dikenal
    tetapi berada di cabang yang kalah. Output: True/False.
    """
    if hash_blok is None or not blok_dikenal(nama_node, hash_blok):
        return False
    kepala_blok = network.panggil_rpc(nama_node, "getblockheader", hash_blok)
    return kepala_blok["confirmations"] >= 1


def periksa_sebelum_disambung(data_percobaan, hasil_undian):
    """
    Cek anti-bocor tepat sebelum penyerang disambung kembali.

    Syarat: penyerang masih terisolasi, tinggi kedua rantai cocok dengan
    hitungan undian (m dan n), blok rahasia belum dikenal merchant/honest,
    blok publik belum dikenal penyerang, dan tx B tidak ada di mempool
    merchant/honest. Melempar GalatVerifikasi jika ada yang dilanggar.
    """
    tinggi_fork = data_percobaan["tinggi_fork"]
    blok_penyerang = hasil_undian["blok_penyerang"]
    blok_jujur = hasil_undian["blok_jujur"]

    pastikan(
        network.jumlah_peer("attacker") == 0,
        "Penyerang tersambung sebelum waktunya",
    )
    tinggi_rahasia = network.panggil_rpc("attacker", "getblockcount")
    tinggi_publik = network.panggil_rpc("merchant", "getblockcount")
    pastikan(
        tinggi_rahasia == tinggi_fork + blok_penyerang,
        f"Tinggi rantai rahasia {tinggi_rahasia} tidak cocok dengan "
        f"m={blok_penyerang}",
    )
    pastikan(
        tinggi_publik == tinggi_fork + blok_jujur,
        f"Tinggi rantai publik {tinggi_publik} tidak cocok dengan "
        f"n={blok_jujur}",
    )

    if blok_penyerang > 0:
        ujung_rahasia = hasil_undian["hash_ujung_rahasia"]
        for nama_node in ("merchant", "honest"):
            pastikan(
                not blok_dikenal(nama_node, ujung_rahasia),
                f"Blok rahasia BOCOR ke {nama_node}",
            )
            pastikan(
                not ada_di_mempool(nama_node, data_percobaan["txid_tx_b"]),
                f"tx B BOCOR ke mempool {nama_node}",
            )
    if blok_jujur > 0:
        ujung_publik = network.panggil_rpc("merchant", "getbestblockhash")
        pastikan(
            not blok_dikenal("attacker", ujung_publik),
            "Blok publik BOCOR ke penyerang",
        )


def tunggu_jaringan_menyatu(hasil_undian):
    """
    Setelah penyerang disambung kembali, tunggu jaringan memilih rantai
    terpanjang. Jika rantai rahasia lebih panjang, merchant dan honest
    pindah ke sana: inilah reorganisasi (reorg).

    Kasus seri (m = n) hanya mungkin saat pengujian tanpa berhenti awal:
    tiap node bertahan di rantai yang dilihatnya lebih dulu sehingga tak
    pernah sepakat; cukup tunggu sampai merchant menerima blok rahasia.
    """
    if hasil_undian["blok_penyerang"] == hasil_undian["blok_jujur"]:
        hash_ujung_rahasia = hasil_undian["hash_ujung_rahasia"]
        for _ in range(100):
            if blok_dikenal("merchant", hash_ujung_rahasia):
                return
            time.sleep(0.1)
        raise TimeoutError("Merchant tidak menerima blok rahasia (seri)")
    network.tunggu_sinkron(list(network.PORT_RPC_NODE))


def ambil_status_wallet_merchant(txid_tx_a):
    """
    Ambil status tx A menurut wallet merchant (sudut pandang penjual).
    Konfirmasi negatif berarti transaksi kalah oleh transaksi tandingan.
    Output: dict ringkas status tx A dan saldo merchant.
    """
    status_tx_a = network.panggil_rpc("merchant", "gettransaction", txid_tx_a)
    saldo = network.panggil_rpc("merchant", "getbalances")["mine"]
    return {
        "konfirmasi": status_tx_a["confirmations"],
        "hash_blok": status_tx_a.get("blockhash"),
        "walletconflicts": status_tx_a.get("walletconflicts", []),
        "mempoolconflicts": status_tx_a.get("mempoolconflicts", []),
        "saldo_terpercaya": saldo["trusted"],
        "saldo_tertunda": saldo["untrusted_pending"],
    }


def tentukan_sukses_di_merchant(data_percobaan, hasil_undian,
                                ujung_publik_lama):
    """
    Tentukan apakah double spending berhasil, dilihat dari node merchant.

    Berhasil jika SEMUA terpenuhi:
    - blok pemuat tx B ada di rantai aktif merchant (tx B terkonfirmasi);
    - tx A hilang: blok pemuatnya tidak di rantai aktif DAN tx A tidak
      kembali ke mempool;
    - cabang publik lama berstatus "valid-fork" (dilewati jika n = 0,
      karena tidak ada cabang publik).

    Cek silang: hasil ini harus sama dengan hasil undian. Jika tidak cocok,
    itu tanda bug, sehingga percobaan dihentikan dengan GalatVerifikasi.
    Output: True (berhasil) / False (gagal).
    """
    txid_tx_a = data_percobaan["txid_tx_a"]
    tx_b_terkonfirmasi = blok_di_rantai_aktif(
        "merchant", hasil_undian["hash_blok_tx_b"]
    )
    blok_tx_a_aktif = blok_di_rantai_aktif(
        "merchant", hasil_undian["hash_blok_tx_a"]
    )
    tx_a_di_mempool = ada_di_mempool("merchant", txid_tx_a)
    tx_a_hilang = not blok_tx_a_aktif and not tx_a_di_mempool

    if hasil_undian["blok_jujur"] == 0:
        cabang_publik_valid_fork = True
    else:
        status_cabang = {}
        for cabang in network.panggil_rpc("merchant", "getchaintips"):
            status_cabang[cabang["hash"]] = cabang["status"]
        cabang_publik_valid_fork = (
            status_cabang.get(ujung_publik_lama) == "valid-fork"
        )

    berhasil = (
        tx_b_terkonfirmasi and tx_a_hilang and cabang_publik_valid_fork
    )

    # Cek silang hasil node dengan hasil undian.
    if hasil_undian["menang_undian"]:
        pastikan(tx_b_terkonfirmasi, "Undian menang, tapi tx B tidak aktif")
        pastikan(not blok_tx_a_aktif, "Undian menang, tapi tx A masih aktif")
        pastikan(not tx_a_di_mempool, "Undian menang, tx A balik ke mempool")
        pastikan(cabang_publik_valid_fork, "Cabang publik bukan valid-fork")
    else:
        pastikan(not tx_b_terkonfirmasi, "Undian kalah, tapi tx B aktif")
        pastikan(
            blok_tx_a_aktif or hasil_undian["blok_jujur"] == 0,
            "Undian kalah, tapi tx A tidak lagi terkonfirmasi",
        )
    pastikan(
        berhasil == hasil_undian["menang_undian"],
        f"Hasil node ({berhasil}) beda dengan hasil undian "
        f"({hasil_undian['menang_undian']})",
    )
    return berhasil


def jalankan_fase_penutup(data_percobaan, hasil_undian):
    """
    Fase penutup satu percobaan (Langkah 6-7): cek anti-bocor, sambungkan
    penyerang, tunggu reorg, lalu tentukan sukses di node merchant.

    Output: dict berisi berhasil (True/False) dan status wallet merchant
    setelah jaringan menyatu.
    """
    periksa_sebelum_disambung(data_percobaan, hasil_undian)
    ujung_publik_lama = network.panggil_rpc("merchant", "getbestblockhash")

    network.sambungkan_kembali_penyerang()
    tunggu_jaringan_menyatu(hasil_undian)

    berhasil = tentukan_sukses_di_merchant(
        data_percobaan, hasil_undian, ujung_publik_lama
    )
    return {
        "berhasil": berhasil,
        "status_merchant_sesudah": ambil_status_wallet_merchant(
            data_percobaan["txid_tx_a"]
        ),
    }


# ---------------------------------------------------------------------------
# Satu percobaan utuh
# ---------------------------------------------------------------------------

def jalankan_satu_percobaan(p, k, seed, sumber_acak=None,
                            pakai_berhenti_awal=True):
    """
    Jalankan satu percobaan serangan double spending berbasis fork.

    Input : p (porsi hashrate penyerang, 0-1), k (konfirmasi yang ditunggu
            merchant), seed (teks seed acak percobaan ini, agar bisa
            diulang). sumber_acak dan pakai_berhenti_awal hanya diubah saat
            pengujian.
    Output: dict berisi berhasil (True/False), m, n, alasan berhenti,
            urutan undian, seed, dan status wallet merchant sebelum
            (saat lunas) dan sesudah reorg.
    Melempar GalatVerifikasi jika ada pengecekan kebenaran yang gagal.
    """
    if sumber_acak is None:
        # Seed berupa teks menghasilkan urutan acak yang sama setiap kali
        # dijalankan, sehingga percobaan dapat diulang persis.
        sumber_acak = random.Random(seed)

    # Langkah 1: mulai dari kondisi bersih dengan dana penyerang yang
    # sudah matang (salinan baseline didanai).
    network.reset_jaringan("baseline_didanai")

    # Langkah 2: siapkan tx A (bayar merchant) & tx B (tandingan), putus
    # penyerang, siarkan tx A ke rantai publik, lalu cek anti-bocor.
    data_percobaan = jalankan_fase_pembuka()

    # Langkah 3: undian blok sejak tx A disiarkan (penyerang menambang
    # paralel). Langkah 4: merchant menganggap lunas saat tx A punya k
    # konfirmasi. Langkah 5: lanjut sampai penyerang menang atau gagal.
    hasil_undian = jalankan_undian_paralel(
        data_percobaan, p, k, sumber_acak, pakai_berhenti_awal
    )

    # Langkah 6: sambungkan penyerang kembali; jaringan memilih rantai
    # terpanjang (reorg jika rantai rahasia lebih panjang).
    # Langkah 7: tentukan sukses di node merchant + cek silang.
    hasil_penutup = jalankan_fase_penutup(data_percobaan, hasil_undian)

    return {
        "berhasil": hasil_penutup["berhasil"],
        "blok_penyerang": hasil_undian["blok_penyerang"],
        "blok_jujur": hasil_undian["blok_jujur"],
        "alasan_berhenti": hasil_undian["status"],
        "urutan_undian": hasil_undian["urutan_undian"],
        "seed": seed,
        "status_merchant_sebelum": hasil_undian["status_merchant_saat_lunas"],
        "status_merchant_sesudah": hasil_penutup["status_merchant_sesudah"],
    }
