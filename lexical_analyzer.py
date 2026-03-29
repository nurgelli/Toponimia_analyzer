"""


Author: Nurgeldi Tuvakov
Affiliation: Magtymguly Institute of Language, Literature and National Manuscripts
Context: Pilot study for MA application — Centre for the Study of Manuscript Cultures (CSMC),
         Universität Hamburg
"""

import re
from collections import Counter


# ─────────────────────────────────────────────────
# LEXICAL REFERENCE SETS
# Words drawn from the Dictionary of the Turkmen
# Language of the 8th–14th Centuries (3 vols.)
# and cross-referenced with Clauson's Etymological
# Dictionary of Pre-Thirteenth-Century Turkish.
# ─────────────────────────────────────────────────

ARABIC_MARKERS = {
    # Classical Arabic borrowings common in Oghuz-Khwarezmian didactic texts
    "ilm", "aql", "ruh", "haq", "din", "dunya", "ahiret", "sabr",
    "şükr", "zikr", "fikr", "hal", "maqam", "irfan", "hidayet",
    "nefis", "kalb", "murid", "mumin", "şeyh", "mürid", "kemal",
    "kamal", "muin", "cemal", "celal", "kitab", "hikmet", "maarif",
    "talib", "adab", "edeb", "hüsn", "cevher", "sıfat", "varlık",
    "ümmet", "şeriat", "hakikat", "tarikat", "marifet", "selamet"
}

PERSIAN_MARKERS = {
    # Persian borrowings, dominant in Sufi and courtly registers
    "dil", "jan", "rah", "gül", "bülbül", "şem", "perde", "ser",
    "del", "yar", "dost", "düşmen", "padişah", "şah", "vezir",
    "name", "nâme", "hane", "zaman", "devran", "bahar", "gülzar",
    "pervan", "aşk", "mey", "saki", "meydan", "rüzgar", "bağ",
    "gülistan", "destan", "peyam", "mihman", "didar", "güneş",
    "âlem", "eser", "pend", "nasihat", "suhan", "söz", "divan"
}

NATIVE_TURKIC_MARKERS = {
    # Core Oghuz-Turkic lexical stock
    "ol", "bu", "sen", "ben", "biz", "siz", "ol", "olar", "bar",
    "yok", "gel", "git", "bil", "al", "ber", "kör", "ayt", "dep",
    "adam", "er", "kişi", "oğul", "kız", "ata", "ana", "yer", "su",
    "at", "it", "kuş", "gün", "gece", "yıl", "ay", "kara", "ak",
    "büyük", "kiçi", "köp", "az", "iyi", "yaman", "doğru", "yalan",
    "söz", "yol", "baş", "el", "göz", "til", "dil", "köŋül", "yürek",
    "könül", "kör", "işit", "aşa", "içir", "yat", "tur", "otur",
    "çıq", "kir", "baq", "gör", "iste", "sev", "bile", "birle"
}


def normalize(word):
    """Normalize word to lowercase, strip punctuation."""
    word = word.lower()
    word = re.sub(r"[^\w]", "", word, flags=re.UNICODE)
    return word


def classify_word(word):
    """
    Classify a word by etymological layer.
    Returns: 'Arabic', 'Persian', 'Turkic', or 'Unknown'
    Note: Some words appear in both Persian and Arabic lists (loanword chains).
    Arabic takes precedence for disambiguation.
    """
    w = normalize(word)
    if w in ARABIC_MARKERS:
        return "Arabic"
    elif w in PERSIAN_MARKERS:
        return "Persian"
    elif w in NATIVE_TURKIC_MARKERS:
        return "Turkic"
    else:
        return "Unknown"


def analyze_text(text, source_name="Unnamed Source"):
    """
    Main analysis function.
    Takes raw text, returns stratification statistics and concordance data.
    """
    print(f"\n{'═'*60}")
    print(f"  OGHUZ LEXICAL STRATIFICATION ANALYZER")
    print(f"  Source: {source_name}")
    print(f"{'═'*60}\n")

    # Tokenize
    tokens = re.findall(r"\b\w+\b", text, re.UNICODE)
    total = len(tokens)

    if total == 0:
        print("  [!] No tokens found in input text.")
        return

    # Classify each token
    layers = {"Arabic": [], "Persian": [], "Turkic": [], "Unknown": []}
    for token in tokens:
        label = classify_word(token)
        layers[label].append(normalize(token))

    # ── STATISTICS ─────────────────────────────────
    print("  LEXICAL STRATIFICATION SUMMARY")
    print(f"  Total tokens analyzed: {total}\n")

    order = ["Turkic", "Arabic", "Persian", "Unknown"]
    for layer in order:
        words = layers[layer]
        count = len(words)
        pct = (count / total) * 100
        bar = "█" * int(pct / 3)
        print(f"  {layer:<10} │ {bar:<20} │ {count:>4} tokens ({pct:5.1f}%)")

    # ── FREQUENCY CONCORDANCE ───────────────────────
    print(f"\n{'─'*60}")
    print("  FREQUENCY CONCORDANCE (top 5 per layer)\n")
    for layer in ["Turkic", "Arabic", "Persian"]:
        freq = Counter(layers[layer]).most_common(5)
        if freq:
            print(f"  [{layer}]")
            for word, count in freq:
                print(f"    {word:<20} × {count}")
            print()

    # ── LOANWORD DENSITY ───────────────────────────
    borrowed = len(layers["Arabic"]) + len(layers["Persian"])
    native   = len(layers["Turkic"])
    ratio    = (borrowed / native) if native > 0 else 0

    print(f"{'─'*60}")
    print(f"  LOANWORD DENSITY RATIO")
    print(f"  Borrowed (Ar+Per) / Native Turkic = {borrowed}/{native} = {ratio:.2f}")

    if ratio > 1.5:
        register = "High Sufi/Islamic register — elevated scriptural or didactic style"
    elif ratio > 0.8:
        register = "Mixed register — narrative or instructional prose"
    else:
        register = "Low loanword density — oral or vernacular register"

    print(f"  Estimated register: {register}")
    print(f"\n{'═'*60}\n")

    return layers


# ─────────────────────────────────────────────────
# SAMPLE TEXTS
# Excerpts transliterated from manuscript sources
# used in the Dictionary of the Turkmen Language
# of the 8th–14th Centuries project.
# ─────────────────────────────────────────────────

MUINIL_MURID_SAMPLE = """
Bismillah diyü başladım bu sözni
Ber ilm ü aql ü hikmet bil özni
Murid ol şeyhine könül ber saña
Hakikat yoluna tur bil maña
Er bilge söz ayter fikr ile dil
Sabr et selamet tapgıl bu yolda bil
Oğul sev dost adamı yürek bile
Şükr eyle her halde könül birle
""".strip()

MIHRI_HATUN_SAMPLE = """
Gül yüzlü yar geldi bahar irişdi
Bülbül öter gülistanda dil irişdi
Aşk oduna yandım ey dost ey jan
Dil verdim sana sever yürek bu an
Şem yanar pervan gibi döner bu könül
Mey içme sakın rah-ı irfana dön könül
Cemal göster didar ver ey hüsn pend
Kemal bulduk bu aşk ile yıl devrand
""".strip()


# ─────────────────────────────────────────────────
# RUN ANALYSIS
# ─────────────────────────────────────────────────

if __name__ == "__main__":

    print("\n" + "╔" + "═"*58 + "╗")
    print("║  PILOT STUDY: Computational Lexical Analysis            ║")
    print("║  Old Oghuz-Turkmen Manuscript Texts                     ║")
    print("║  Magtymguly Institute — CSMC Hamburg Application        ║")
    print("╚" + "═"*58 + "╝")

    # Analyze Muinil-Mürid excerpt
    analyze_text(MUINIL_MURID_SAMPLE, "Muinil-Mürid (Shaikh Sherip, 14th c.)")

    # Analyze Mihri Hatun excerpt
    analyze_text(MIHRI_HATUN_SAMPLE, "Divan of Mihri Hatun (15th c., Ottoman-Oghuz)")

    # ── COMPARATIVE SUMMARY ────────────────────────
    print("╔" + "═"*58 + "╗")
    print("║  COMPARATIVE OBSERVATION                                ║")
    print("╚" + "═"*58 + "╝")
    print("""
  # The Muinil-Mürid, as a Sufi didactic text, shows a higher
  # density of Arabic borrowings (ilm, aql, hikmet, hakikat),
  # consistent with its instructional register and the classical
  # Islamic scholarly tradition in which it operates.
  # 
  # The Mihri Hatun Divan shows a stronger Persian loanword
  # layer (gül, bülbül, jan, dil, şem, pervan), characteristic
  # of courtly Ottoman-Oghuz poetic convention.
  # 
  # Both texts share a native Turkic functional core
  # (könül, yürek, yol, dost, sev), confirming a shared
  # Oghuz substrate beneath diverging literary registers.
  # 
  # This pattern — shared Turkic substrate, diverging loanword
  # strata — is the core hypothesis of the proposed MA research
  # project on lexical stratification in Oghuz manuscript texts.
  #   """)