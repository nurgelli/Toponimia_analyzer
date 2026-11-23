import re
from collections import Counter



ARABIC_MARKERS = {
    "ylym", "akl", "ruh", "hak",  "dünýä", "ahyrýet", "sabyr",
    "şükür", "zikir", "pikir", "hal", "makam", "yrfan",
    "nebis", "kalp", "mürit", "mömin", "şeýh",  "kemal",
    "kemal", "mugyn", "cemal", "jelal", "kitap", "hikmet", "magaryf",
    "talyp", "edep", "hüsni-jemal", "jöwher", "sypat", "barlyk",  
    "hakykat", "tarykat", "salamat"
} # Need to attach arabic dictionary

PERSIAN_MARKERS = {
    # Persian borrowings, dominant in Sufi and courtly registers
    "dil", "jan", "rah", "gül", "bilbil", "şem", "perde", "ser",
    "del", "ýar", "dost", "duşman", "patyşa", "şah", "wezir",
    "nama", "hana", "zaman", "döwran", "bahar", "gülzar",
    "perwana", "meý", "saky", "meýdan",  "bag", "bagban",
    "gülistan", "dessan", "myhman", "didar", "güneş",
    "älem", "eser", "pent", "nesihat", "suwhan", "söz", "diwan"
} # Need to attach Persian dictionary

NATIVE_TURKIC_MARKERS = {

    "ol", "bu", "sen", "ben", "biz", "siz", "bol", "olar", "bar",
    "yok", "gel", "git", "bil", "al", "ber", "kör", "aýt", "dep",
    "adam", "är", "kişi", "ogul", "gyz", "ata", "ene", "ýer", "sus",
    "at", "it", "guş", "gün", "gije", "ýyl", "aý", "gara", "ak",
    "uly", "kiçi", "köp", "az", "gowy", "ýaman", "dogry", "ýalan",
    "söz", "ýol", "baş", "el", "göz", "til", "dil", "köňül", "ýürek",
    "kör", "eşit", "aşa", "içir", "ýat", "tur", "otur",
    "çyk", "gir", "bak", "gör", "isle", "söý", "bile", "birle"
} # Need to attach arabic dictionary


def normalize(word):
    word = word.lower()
    word = re.sub(r"[^\w]", "", word, flags=re.UNICODE)
    return word


def classify_word(word):
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

    print(f"\n{'═'*60}")
    print(f"  OGHUZ LEXICAL STRATIFICATION ANALYZER")
    print(f"  Source: {source_name}")
    print(f"{'═'*60}\n")


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

    print(f"\n{'─'*60}")
    print("  FREQUENCY CONCORDANCE (top 5 per layer)\n")
    for layer in ["Turkic", "Arabic", "Persian"]:
        freq = Counter(layers[layer]).most_common(5)
        if freq:
            print(f"  [{layer}]")
            for word, count in freq:
                print(f"    {word:<20} × {count}")
            print()

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
# Later need to change this with whole source

MIHRI_HATUN_SAMPLE = """
Gül yüzlü yar geldi bahar irişdi
Bülbül öter gülistanda dil irişdi
Aşk oduna yandım ey dost ey jan
Dil verdim sana sever yürek bu an
Şem yanar pervan gibi döner bu könül
Mey içme sakın rah-ı irfana dön könül
Cemal göster didar ver ey hüsn pend
Kemal bulduk bu aşk ile yıl devrand
""".strip() # Later need to change this with whole source


if __name__ == "__main__":

    print("\n" + "╔" + "═"*58 + "╗")
    print("║  Old Oghuz-Turkmen Manuscript Texts                     ║")
    print("╚" + "═"*58 + "╝")

    analyze_text(MUINIL_MURID_SAMPLE, "Muinil-Mürid (Shaikh Sherip, 14th c.)")

    analyze_text(MIHRI_HATUN_SAMPLE, "Divan of Mihri Hatun (15th c., Ottoman-Oghuz)")

    print("╔" + "═"*58 + "╗")
    print("║  COMPARATIVE OBSERVATION                                ║")
    print("╚" + "═"*58 + "╝")