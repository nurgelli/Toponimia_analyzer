# Türkmen adları için Word denetleyicisi (MVP)

Excel'deki standart kişi, yer, ülke ve diğer adları ile bilinen yanlış yazım biçimlerini yerel SQLite sözlüğüne alır. Yüklenen `.docx` belgelerini tarar; kayıtlı yanlış varyantları kırmızı, modelin olası yazım tahminlerini mavi işaretler ve işlenmiş belgeyi indirmeye sunar.

## Excel şeması

İlk çalışma sayfasındaki ilk üç sütun kullanılır. Başlık satırı isteğe bağlıdır.

| Sütun | İçerik | Örnek |
|---|---|---|
| A | Standart/doğru ad | Ali |
| B | Adın türü veya etiketi | İnsan ady |
| C | Yanlış yazımlar; virgül, noktalı virgül, `|` veya satır sonuyla ayrılabilir | `[Aly, Äli, Äly]` |

Her yanlış yazım ayrı bir varyant olarak saklanır. Aynı dosyayı tekrar yüklemek mevcut kayıtları çoğaltmaz. Yeni yüklenen kayıtlar sözlüğe eklenir.

## Kurulum ve başlatma

Python 3.10 veya üstü gerekir.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

Tarayıcıda `http://127.0.0.1:8000` adresini açın. Önce `.xlsx` sözlüğünü, ardından `.docx` belgesini yükleyin. SQLite veritabanı `data/names.sqlite3` içinde, işlenmiş Word dosyaları `data/processed/` içinde saklanır. Veri dizinini değiştirmek için uygulamayı başlatmadan önce `TXT_ANALYZER_DATA_DIR` ortam değişkenini ayarlayın.

## MVP kapsamı

- Uygulama Excel varyantları üzerinde karakter n-gram TF-IDF en yakın komşu modelini her belge taramasında yeniden eğitir. Bilinen varyantlar kırmızı, yeterince benzer olup Excel'de birebir bulunmayan olası yazımlar mavi işaretlenir.
- Mavi sonuç, en yakın kayıtlı varyantı ve benzerlik puanını raporlar. Puan olasılık değildir; tahminler belgeyi otomatik değiştirmez. Küçük veya belirsiz eşleşmeler için tahmin eşiği kullanılır.
- Excel yüklemeleri var olan sözlüğe eklenir. Ana sayfadaki sıfırlama düğmesi bütün sözlük kayıtlarını siler; sonraki belge taraması yeni Excel verileriyle modeli yeniden oluşturur.
- Kırmızı eşleşmeler Excel listesine göre tamdır; mavi tahminler karakter benzerliği modelinin önerileridir.
- Harf büyüklüğü dikkate alınmaz; Türkmen harfleri korunur. Eşleşmeler kelime sınırlarına göre aranır.
- Gövde metni, tablolar, üstbilgi ve altbilgiler taranır. “Awtomatiki düzetmelimi?” seçeneği işaretlenirse yalnızca kırmızı eşleşmeler standart adla değiştirilir; mavi tahminlere dokunulmaz.
- Word biçimi `.docx` olmalıdır. Eski `.doc` dosyalarını önce Word'de `.docx` olarak kaydedin.
- Şu an C sütununda varyantların virgülle ayrılması, varyantın kendisinde virgül içeren adlar için uygun değildir.
