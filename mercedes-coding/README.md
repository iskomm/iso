# Mercedes-Benz Kodlama Uygulaması (OpenPort 2.0 / J2534)

CBF dosyalarından çıkarılan tanımlarla Mercedes beyinlerinde (ECU) variant
coding okuma/yazma yapan, **security access (seed/key)** destekli bir araç.
OpenPort 2.0 (Tactrix) J2534 pass-thru cihazı ile çalışır.

> ⚠️ **Sorumluluk reddi.** Araç kodlaması risklidir. Yanlış değer yazmak
> beyni kullanılamaz hale getirebilir. Yalnızca kendi aracınızda, ne
> yaptığınızı bilerek ve **her zaman önce yedek alarak** kullanın. Airbag,
> ESP, fren, emniyet sistemlerine dokunmayın. Bu yazılım "olduğu gibi"
> sunulur; hiçbir garanti vermez.

## Mimari

```
src/
  j2534.py     OpenPort 2.0 J2534 sarmalayıcısı (ISO15765 / CAN)
  uds.py       UDS (ISO 14229) + kısmi KWP2000 istemcisi
  security.py  Seed/key (27) çerçevesi: XOR/Add/LFSR örnekleri + DLL köprüsü
  cbf.py       CBF dosya tarayıcı + kodlama tanım modeli (JSON)
  coding.py    Yüksek seviye motor: oku/yedekle/yaz/doğrula + restore
  cli.py       Komut satırı arayüzü
  app.py       Tkinter grafik arayüzü
defs/
  w176_sam_example.json   Örnek kodlama tanımı (şema referansı)
tests/         Donanımsız çalışan birim testleri (sahte ECU)
```

Tasarım ilkesi: **iş mantığı transport'tan bağımsızdır.** `UdsClient` sadece
`send/recv` sağlayan bir nesne ister; bu yüzden tüm UDS/security/coding
mantığı donanım olmadan, sahte bir ECU ile test edilebilir.

## Kurulum

- **Windows** + **32-bit Python** (OpenPort sürücüsü `op20pt32.dll` 32-bittir).
- Tactrix OpenPort 2.0 sürücüsü kurulu olmalı (J2534 kaydını yapar).
- Harici Python paketi gerekmez; testler için `pip install pytest`.

```bash
python -m src.app        # GUI
python -m src.cli --help # komut satırı
python -m pytest         # testler (her platformda çalışır)
```

## Kullanım akışı

1. **CBF'i tara:** `python -m src.cli scan araba.cbf`
   Beyin adını ve kodlama etiketlerini listeler.
2. **Tanım hazırla:** `defs/w176_sam_example.json`'u kopyalayıp kendi
   CBF'inden (CaesarSuite ile) çıkardığın gerçek DID, byte/bit konumları ve
   CAN ID'leri ile doldur.
3. **Oku:** `python -m src.cli read defs/senin.json --block konfor_isiklandirma`
4. **Yaz (önce yedek):**
   ```bash
   python -m src.cli set defs/senin.json --block konfor_isiklandirma \
       --field coming_home=1 --field konfor_sinyal_sayisi=5 \
       --backup yedek.json --level 3 --seedkey-dll C:\yol\seedkey.dll
   ```
5. **Gerekirse geri yükle:**
   `python -m src.cli restore defs/senin.json yedek.json`

## Security Access (seed/key) — önemli

Mercedes'in **gerçek, beyne özel seed/key algoritması CBF'in içinde
değildir**; ayrı (çoğu zaman imzalı) DLL'lerde bulunur. Bu yüzden `security.py`
iki yol sunar:

- **`DllSeedKey`** — Mercedes orijinal seed/key DLL'ini yükler ve
  `GenerateKeyEx(seed, len, secParam, key, &keyLen)` imzalı fonksiyonu çağırır.
  **Gerçek kullanım yolu budur.** Fonksiyon adı DLL'e göre ayarlanabilir.
- **Saf-Python örnekler** (`XorKey`, `AddConstantKey`, `LfsrRotateKey`) —
  test edilebilir ve bazı eski KWP beyinlerinde işe yarayan şablonlar; çoğu
  beyinde yalnızca örnektir.

Tanım JSON'ında:
```json
"seedkey": { "level": 3, "dll": "C:\\yol\\seedkey.dll", "func": "GenerateKeyEx" }
```

## CBF ayrıştırma hakkında dürüst not

Tam CBF semantik ayrıştırması (tüm variant'lar, servisler, scaling
formülleri) çok kapsamlıdır; en iyi açık referans
[CaesarSuite](https://github.com/jglim/CaesarSuite)'tir. Bu projedeki
`CbfFile` **en-iyi-çaba** yapısal tarama yapar (beyin/varyant tanıma, etiket
çıkarma). Güvenli okuma/yazma, elle ya da CaesarSuite ile hazırlanan JSON
**tanım** üzerinden yürür — böylece uygulama CBF ayrıştırması tam olmasa da
hemen kullanılabilir.

## Test

```bash
python -m pytest -q      # 21 test, donanım gerektirmez
```
Testler sahte bir UDS ECU'su (`tests/fake_transport.py`) ile oturum kontrolü,
negatif cevaplar, responsePending bekleme, seed/key el sıkışması, bit
okuma/yazma ve yedek/geri-yükleme akışını doğrular.
