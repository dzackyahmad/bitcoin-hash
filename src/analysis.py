"""
analysis.py — Tahap 4: tabel dan grafik tingkat keberhasilan double spending.

Dari results/hasil_percobaan.csv dihitung persentase keberhasilan tiap
kombinasi (p, k) = jumlah berhasil ÷ N × 100%, lalu dibandingkan dengan
prediksi model Nakamoto (2008) dengan z = k (lihat brief/Dokumentasi.md T8).
Tanpa interval kepercayaan 95% (disederhanakan, lihat brief/CLAUDE.md).

Output:
- results/tabel_keberhasilan_empiris.csv   persentase empiris, baris p × kolom k
- results/tabel_prediksi_nakamoto.csv      persentase Nakamoto, baris p × kolom k
- figures/keberhasilan_vs_nakamoto.png     grafik garis empiris vs Nakamoto

Cara pakai (dari root proyek):
    python src/analysis.py
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # simpan ke file saja, tanpa jendela
import matplotlib.pyplot as plt
import pandas as pd

FOLDER_PROYEK = Path(__file__).resolve().parent.parent
FILE_CSV_HASIL = FOLDER_PROYEK / "results" / "hasil_percobaan.csv"
FOLDER_RESULTS = FOLDER_PROYEK / "results"
FOLDER_FIGURES = FOLDER_PROYEK / "figures"

# Warna garis per p: satu hue biru, terang (p kecil) ke gelap (p besar),
# karena p adalah besaran berurutan. Sembilan tingkat satu hue tidak cukup
# berbeda untuk dibedakan dari warna saja, jadi tiap garis juga diberi label
# p langsung di ujungnya, ditambah legenda.
WARNA_P = [
    "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
    "#256abf", "#1c5cab", "#104281", "#0d366b",
]
WARNA_TEKS = "#0b0b0b"
WARNA_TEKS_SEKUNDER = "#52514e"
WARNA_GRID = "#e4e3df"
WARNA_LATAR = "#fcfcfb"

# Label p di ujung garis hanya untuk p yang garisnya cukup renggang di k = 6;
# garis p kecil menumpuk dekat 0% dan diberi satu label kelompok.
P_BERLABEL_MIN = 0.25


def baca_hasil(file_csv):
    """
    Baca CSV hasil percobaan. Kolom p dibaca sebagai teks ("0.05") agar sama
    persis dengan seed, dan kolom berhasil sebagai True/False.
    Output: DataFrame.
    """
    return pd.read_csv(
        file_csv, dtype={"p": str, "k": int, "berhasil": str}
    ).assign(berhasil=lambda d: d["berhasil"] == "True")


def tabel_keberhasilan_empiris(data):
    """
    Persentase keberhasilan tiap (p, k) = jumlah berhasil ÷ N × 100%.
    Output: DataFrame dengan baris p dan kolom k.
    """
    ringkas = data.groupby(["p", "k"])["berhasil"].agg(["sum", "count"])
    persen = ringkas["sum"] / ringkas["count"] * 100
    return persen.unstack("k")


def peluang_nakamoto(q, z):
    """
    Peluang penyerang dengan porsi hashrate q akhirnya menyusul dari z blok
    di belakang, menurut Nakamoto (2008) bagian 11:

        lambda = z * q / p,   p = 1 - q
        P = 1 - sum_{i=0..z} Poisson(i; lambda) * (1 - (q/p)^(z - i))

    Pada z = 0 rumus ini memberi 1; di riset ini k = 0 adalah titik kontrol,
    bukan uji langsung ke rumus (brief/Dokumentasi.md T8).
    Output: peluang (0–1).
    """
    p = 1 - q
    lam = z * q / p
    jumlah = 0.0
    for i in range(z + 1):
        poisson = math.exp(-lam) * lam ** i / math.factorial(i)
        jumlah = jumlah + poisson * (1 - (q / p) ** (z - i))
    return 1 - jumlah


def tabel_prediksi_nakamoto(daftar_p, daftar_k):
    """
    Persentase prediksi Nakamoto tiap (p, k) dengan z = k.
    Input: daftar p (teks, mis. "0.05") dan daftar k.
    Output: DataFrame dengan baris p dan kolom k.
    """
    return pd.DataFrame(
        [[peluang_nakamoto(float(p), k) * 100 for k in daftar_k]
         for p in daftar_p],
        index=pd.Index(daftar_p, name="p"),
        columns=pd.Index(daftar_k, name="k"),
    )


def simpan_tabel(tabel, file_csv):
    """Simpan tabel persentase (baris p × kolom k) ke CSV, 2 desimal."""
    tabel.round(2).to_csv(file_csv)


def gambar_grafik(empiris, nakamoto, file_png):
    """
    Grafik garis: sumbu X = k, satu garis per p. Garis penuh bertitik =
    empiris; garis putus-putus berwarna sama = prediksi Nakamoto (z = k),
    digambar mulai k = 1 karena di k = 0 rumus memberi 100% (titik kontrol).
    """
    daftar_k = list(empiris.columns)
    k_nakamoto = [k for k in daftar_k if k >= 1]
    gambar, sumbu = plt.subplots(figsize=(11, 6.5), dpi=150)
    gambar.patch.set_facecolor(WARNA_LATAR)
    sumbu.set_facecolor(WARNA_LATAR)

    for warna, p in zip(WARNA_P, empiris.index):
        sumbu.plot(k_nakamoto, nakamoto.loc[p, k_nakamoto], color=warna,
                   linestyle=(0, (4, 3)), linewidth=1.5)
        sumbu.plot(daftar_k, empiris.loc[p], color=warna, linewidth=2,
                   marker="o", markersize=5, label=f"p = {p}")

    # Label p di ujung kanan garis empiris yang cukup renggang, ditambah satu
    # label kelompok untuk garis p kecil yang menumpuk dekat 0%.
    k_akhir = daftar_k[-1]
    p_kecil = [p for p in empiris.index if float(p) < P_BERLABEL_MIN]
    for p in empiris.index:
        if float(p) >= P_BERLABEL_MIN:
            sumbu.annotate(f"p = {p}", xy=(k_akhir, empiris.loc[p, k_akhir]),
                           xytext=(8, 0), textcoords="offset points",
                           fontsize=8.5, color=WARNA_TEKS_SEKUNDER,
                           va="center")
    if p_kecil:
        sumbu.annotate(f"p = {p_kecil[0]}–{p_kecil[-1]}",
                       xy=(k_akhir, 0), xytext=(8, -2),
                       textcoords="offset points", fontsize=8.5,
                       color=WARNA_TEKS_SEKUNDER, va="top")

    # Legenda gaya garis (empiris vs Nakamoto), terpisah dari legenda p.
    gaya = [
        plt.Line2D([], [], color=WARNA_TEKS_SEKUNDER, linewidth=2,
                   marker="o", markersize=5, label="Empiris (regtest, N = 1.000)"),
        plt.Line2D([], [], color=WARNA_TEKS_SEKUNDER, linewidth=1.5,
                   linestyle=(0, (4, 3)), label="Prediksi Nakamoto (z = k)"),
    ]
    # Kedua legenda di luar area grafik (kanan) agar tidak menutupi garis.
    legenda_p = sumbu.legend(loc="upper left", bbox_to_anchor=(1.10, 1.0),
                             fontsize=8.5, frameon=False,
                             title="Porsi hashrate\npenyerang (p)",
                             title_fontsize=8.5, alignment="left")
    sumbu.add_artist(legenda_p)
    sumbu.legend(handles=gaya, loc="lower left", bbox_to_anchor=(1.10, 0.0),
                 fontsize=8.5, frameon=False)

    sumbu.set_xlim(-0.2, k_akhir + 0.2)
    sumbu.set_ylim(0, 105)
    sumbu.set_xticks(daftar_k)
    sumbu.set_xlabel("Jumlah konfirmasi yang ditunggu merchant (k)",
                     color=WARNA_TEKS)
    sumbu.set_ylabel("Tingkat keberhasilan double spending (%)",
                     color=WARNA_TEKS)
    sumbu.set_title(
        "Tingkat keberhasilan double spending: empiris vs prediksi Nakamoto",
        color=WARNA_TEKS, fontsize=11, loc="left",
    )
    sumbu.text(0, -0.12, "Nakamoto di k = 0 bernilai 100% (titik kontrol, "
               "tidak digambar).", transform=sumbu.transAxes, fontsize=8,
               color=WARNA_TEKS_SEKUNDER)
    sumbu.grid(True, color=WARNA_GRID, linewidth=0.8)
    sumbu.set_axisbelow(True)
    for sisi in ("top", "right"):
        sumbu.spines[sisi].set_visible(False)
    for sisi in ("left", "bottom"):
        sumbu.spines[sisi].set_color(WARNA_GRID)
    sumbu.tick_params(colors=WARNA_TEKS_SEKUNDER)

    gambar.tight_layout()
    gambar.savefig(file_png, facecolor=WARNA_LATAR)
    plt.close(gambar)


def main():
    """Hitung tabel empiris & Nakamoto, simpan, lalu gambar grafiknya."""
    data = baca_hasil(FILE_CSV_HASIL)
    empiris = tabel_keberhasilan_empiris(data)
    nakamoto = tabel_prediksi_nakamoto(list(empiris.index),
                                       list(empiris.columns))

    FOLDER_FIGURES.mkdir(exist_ok=True)
    simpan_tabel(empiris, FOLDER_RESULTS / "tabel_keberhasilan_empiris.csv")
    simpan_tabel(nakamoto, FOLDER_RESULTS / "tabel_prediksi_nakamoto.csv")
    gambar_grafik(empiris, nakamoto,
                  FOLDER_FIGURES / "keberhasilan_vs_nakamoto.png")

    print("Tingkat keberhasilan empiris (%):")
    print(empiris.round(1).to_string())
    print("\nPrediksi Nakamoto (%), z = k:")
    print(nakamoto.round(1).to_string())


if __name__ == "__main__":
    main()
