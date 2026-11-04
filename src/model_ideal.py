"""
model_ideal.py — Tahap 5: model matematis murni perlombaan double spending.

Dipakai untuk menjelaskan selisih hasil Bitcoin Core dengan prediksi Nakamoto.
Ditulis langsung dari definisi matematisnya, TIDAK menyalin trial.py, agar
bisa dipakai sebagai pembanding independen.

Definisi model (q = porsi hashrate penyerang):
- Penyerang (m) dan jujur (n) mulai bersamaan dari titik fork, m = n = 0,
  tanpa pre-mine. Tiap blok berikutnya milik penyerang dengan peluang q,
  selain itu milik jujur: Bernoulli(q) per blok.
- Merchant lunas saat n >= k (blok pemuat pembayaran = konfirmasi ke-1).
- Penyerang menang saat lunas dan rantainya unggul: m > n, atau m >= n bila
  seri dihitung menang.
- Batas give-up (opsional): serangan gagal begitu n mencapai batas.

Isi:
- simulasi_mc            Monte Carlo (numpy) untuk aturan apa pun.
- peluang_tepat_tanpa_batas  rumus eksak tanpa batas give-up
                         (binomial negatif + gambler's ruin).
- peluang_tepat_dp       peluang eksak lewat pemrograman dinamis, aturan apa pun.
- bandingkan_dengan_core Langkah 1: aturan kita vs Bitcoin Core per sel.
- tabel_ablation         Langkah 2: sumbangan tiap aturan pada selisih ke
                         Nakamoto.

Cara pakai (dari root proyek), menulis ulang dua CSV hasil Tahap 5:
    python src/model_ideal.py
"""

import math

import numpy as np

# Toleransi pemotongan untuk aturan tanpa batas give-up: perlombaan dihentikan
# (dihitung gagal) bila penyerang tertinggal D blok setelah lunas, dengan D
# dipilih agar peluang menyusul dari D blok di belakang < 1e-9.
TOLERANSI_POTONG = 1e-9


def tertinggal_maksimum(q):
    """
    D terkecil dengan (q/(1-q))^D < TOLERANSI_POTONG. Pemotongan ini hanya
    teknis (perlombaan tanpa batas tidak bisa disimulasikan tanpa akhir),
    bukan aturan give-up. Output: bilangan bulat D.
    """
    rasio = q / (1 - q)
    return math.ceil(math.log(TOLERANSI_POTONG) / math.log(rasio))


def simulasi_mc(q, k, jumlah, seri_menang, batas_jujur, rng,
                syarat_lunas=True):
    """
    Monte Carlo perlombaan blok untuk satu (q, k).

    Input : q, k, jumlah percobaan, seri_menang (True/False), batas_jujur
            (bilangan bulat, atau None = tanpa batas give-up), rng (numpy
            Generator), syarat_lunas (False = penyerang boleh menang sebelum
            merchant lunas).
    Output: peluang menang (0–1).
    """
    m = np.zeros(jumlah, dtype=np.int64)
    n = np.zeros(jumlah, dtype=np.int64)
    aktif = np.ones(jumlah, dtype=bool)
    menang = np.zeros(jumlah, dtype=bool)
    d_maks = tertinggal_maksimum(q) if batas_jujur is None else None

    while True:
        # Status dicek di awal (m = n = 0) dan setelah tiap blok.
        lunas = (n >= k) if syarat_lunas else np.ones(jumlah, dtype=bool)
        unggul = (m >= n) if seri_menang else (m > n)
        baru_menang = aktif & lunas & unggul
        if batas_jujur is None:
            baru_gagal = aktif & ~baru_menang & lunas & (n - m >= d_maks)
        else:
            baru_gagal = aktif & ~baru_menang & (n >= batas_jujur)
        menang |= baru_menang
        aktif &= ~(baru_menang | baru_gagal)

        indeks = np.flatnonzero(aktif)
        if indeks.size == 0:
            break
        blok_penyerang = rng.random(indeks.size) < q
        m[indeks[blok_penyerang]] += 1
        n[indeks[~blok_penyerang]] += 1

    return menang.mean()


def peluang_tepat_tanpa_batas(q, k, seri_menang):
    """
    Peluang eksak tanpa batas give-up (perlombaan tak terbatas), dengan
    syarat lunas n >= k.

    Saat jujur menemukan blok ke-k, jumlah blok penyerang M berdistribusi
    binomial negatif: P(M = j) = C(j+k-1, j) (1-q)^k q^j. Dari tertinggal d
    blok, peluang penyerang suatu saat menyusul = (q/(1-q))^d (gambler's
    ruin). Seri menang: perlu menyusul sampai sama (d = k - j); seri kalah:
    perlu unggul satu (d = k - j + 1).
    Output: peluang (0–1).
    """
    rasio = q / (1 - q)
    if k == 0:
        # Lunas sejak awal di posisi seri (m = n = 0).
        return 1.0 if seri_menang else rasio
    total = 0.0
    for j in range(5000):
        pmf = math.comb(j + k - 1, j) * (1 - q) ** k * q ** j
        tertinggal = (k - j) if seri_menang else (k - j + 1)
        total += pmf * (1.0 if tertinggal <= 0 else rasio ** tertinggal)
        if j > k and pmf < 1e-18:
            break
    return total


def peluang_tepat_dp(q, k, seri_menang, batas_jujur, syarat_lunas=True):
    """
    Peluang eksak lewat pemrograman dinamis: sebaran peluang atas keadaan
    (m, n) yang belum selesai digeser satu blok tiap langkah, dengan aturan
    status yang sama seperti simulasi_mc. Tanpa batas give-up, pemotongan
    tertinggal_maksimum dipakai dan iterasi berhenti saat sisa peluang
    < 1e-13.
    Output: peluang menang (0–1).
    """
    d_maks = tertinggal_maksimum(q) if batas_jujur is None else None
    sebaran = {(0, 0): 1.0}
    peluang_menang = 0.0
    while sebaran:
        lanjut = {}
        for (m, n), peluang in sebaran.items():
            lunas = (n >= k) if syarat_lunas else True
            unggul = (m >= n) if seri_menang else (m > n)
            if lunas and unggul:
                peluang_menang += peluang
                continue
            if batas_jujur is None:
                if lunas and n - m >= d_maks:
                    continue
            elif n >= batas_jujur:
                continue
            for keadaan, bobot in (((m + 1, n), q), ((m, n + 1), 1 - q)):
                lanjut[keadaan] = lanjut.get(keadaan, 0.0) + peluang * bobot
        sebaran = lanjut
        if sum(sebaran.values()) < 1e-13:
            break
    return peluang_menang


# ---------------------------------------------------------------------------
# Langkah 1: aturan eksperimen kita vs hasil Bitcoin Core
# ---------------------------------------------------------------------------

# Aturan eksperimen (lihat tentukan_status di trial.py, dirumuskan ulang):
# menang bila n >= k dan m > n; gagal bila n mencapai 20 lebih dulu.
ATURAN_KITA = {"seri_menang": False, "batas_jujur": 20}


def bandingkan_dengan_core(empiris, jumlah_mc, rng):
    """
    Untuk tiap sel (p, k): persen Bitcoin Core, persen MC aturan kita
    (jumlah_mc percobaan), persen eksak aturan kita (DP), dan skor z selisih
    Core terhadap eksak dengan N Core = 1.000.
    Input : empiris = tabel persen Core (baris p teks, kolom k).
    Output: DataFrame satu baris per sel.
    """
    import pandas as pd

    baris = []
    for p in empiris.index:
        for k in empiris.columns:
            q = float(p)
            core = empiris.loc[p, k]
            mc = simulasi_mc(q, k, jumlah_mc, rng=rng, **ATURAN_KITA) * 100
            eksak = peluang_tepat_dp(q, k, **ATURAN_KITA) * 100
            se = math.sqrt(max(eksak * (100 - eksak), 1e-9) / 1000)
            baris.append({
                "p": p, "k": k, "core": core, "mc": mc, "eksak": eksak,
                "core_min_mc": core - mc, "core_min_eksak": core - eksak,
                "z_core_vs_eksak": (core - eksak) / se,
            })
    return pd.DataFrame(baris)


# ---------------------------------------------------------------------------
# Langkah 2: ablation sumber gap ke Nakamoto
# ---------------------------------------------------------------------------

# Varian aturan; tiap varian mengubah satu aturan dari aturan kita.
VARIAN_ATURAN = {
    "A_aturan_kita": {"seri_menang": False, "batas_jujur": 20},
    "B_seri_menang": {"seri_menang": True, "batas_jujur": 20},
    "C_tanpa_batas": {"seri_menang": False, "batas_jujur": None},
    "D_seri_menang_tanpa_batas": {"seri_menang": True, "batas_jujur": None},
}


def tabel_ablation(daftar_sel, peluang_nakamoto):
    """
    Persen eksak (DP) tiap varian aturan untuk tiap sel (p, k), ditambah
    rumus Nakamoto, dan pemecahan gap Nakamoto - aturan kita:
    - aproksimasi_poisson = Nakamoto - D (rumus vs model eksak konvensinya)
    - efek_seri  = B - A   (seri dihitung menang, batas 20 tetap)
    - efek_batas = C - A   (batas dihapus, seri tetap kalah)
    - interaksi  = (D - A) - efek_seri - efek_batas
    Input : daftar (p teks, k), fungsi peluang_nakamoto(q, z).
    Output: DataFrame satu baris per sel.
    """
    import pandas as pd

    baris = []
    for p, k in daftar_sel:
        q = float(p)
        nilai = {nama: peluang_tepat_dp(q, k, **aturan) * 100
                 for nama, aturan in VARIAN_ATURAN.items()}
        nakamoto = peluang_nakamoto(q, k) * 100
        a, b = nilai["A_aturan_kita"], nilai["B_seri_menang"]
        c, d = nilai["C_tanpa_batas"], nilai["D_seri_menang_tanpa_batas"]
        baris.append({
            "p": p, "k": k, "nakamoto": nakamoto, **nilai,
            "gap_total": nakamoto - a,
            "aproksimasi_poisson": nakamoto - d,
            "efek_seri": b - a,
            "efek_batas": c - a,
            "interaksi": (d - a) - (b - a) - (c - a),
        })
    return pd.DataFrame(baris)


# Seed MC Langkah 1 (dicatat agar kolom mc dapat diulang persis).
SEED_MC_LANGKAH1 = 20261104


def main():
    """Tulis ulang CSV Langkah 1 dan Langkah 2 ke results/."""
    import analysis

    empiris = analysis.tabel_keberhasilan_empiris(
        analysis.baca_hasil(analysis.FILE_CSV_HASIL)
    )
    langkah1 = bandingkan_dengan_core(
        empiris, 1000, np.random.default_rng(SEED_MC_LANGKAH1)
    )
    langkah1.round(3).to_csv(
        analysis.FOLDER_RESULTS / "model_ideal_langkah1_core_vs_model.csv",
        index=False,
    )

    sel = [(p, k) for p in empiris.index for k in empiris.columns if k >= 1]
    langkah2 = tabel_ablation(sel, analysis.peluang_nakamoto)
    langkah2.round(3).to_csv(
        analysis.FOLDER_RESULTS / "model_ideal_langkah2_ablation.csv",
        index=False,
    )
    print("Langkah 1 dan Langkah 2 ditulis ke results/.")


if __name__ == "__main__":
    main()
