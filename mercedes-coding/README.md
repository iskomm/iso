# Mercedes-Benz Kodlama Uygulaması (OpenPort 2.0 / J2534)

Bütün Mercedes platformları için (W176, W177, W205, W213, W222) variant
coding okuma/yazma, **tek tıkla özellik aktivasyonu (AMG Menü dahil)**,
beyin başına **arıza oku/sil ve tekrar tanıtma (teach-in)** yapan,
**security access (seed/key)** destekli bir araç. OpenPort 2.0 (Tactrix)
J2534 pass-thru cihazı ile çalışır.

## Hızlı başlangıç (direkt uygulama)

```bash
python mercedes_coding.py      # GUI (Windows'ta Baslat.bat çift tık)
```

### Tek dosya .exe (Windows, kurulum gerektirmez)

```bash
build_exe.bat                  # -> dist\MercedesKodlama.exe
```
PyInstaller ile tanım kütüphanesi (defs/) içine gömülü tek `.exe` üretir;
çift tıkla çalışır. OpenPort sürücüsü 32-bit olduğundan 32-bit Python ile
derleyin.

GUI açılışta gömülü tanım kütüphanesini yükler. Akış: **Model/beyin seç →
Bağlan → Oturum Aç →** üç sekme:
- **Özellikler:** tek tıkla aç/kapat. `★ AMG Menü Aktivasyonu` her modelde var.
- **Arıza & Tanıtma:** arızaları oku (okunabilir kod + durum), sil,
  "Sil + Tekrar Tanıt" (far beyni/konfor beyni değişimi sonrası).
- **Gelişmiş:** blok/alan bazlı manuel okuma/yazma.

`VIN ile Tanı` butonu beynin VIN'ini okuyup modeli otomatik seçer.

> ⚠️ **Sorumluluk reddi.** Araç kodlaması risklidir. Yanlış değer yazmak
> beyni kullanılamaz hale getirebilir. Yalnızca kendi aracınızda, ne
> yaptığınızı bilerek ve **her zaman önce yedek alarak** kullanın. Airbag,
> ESP, fren, emniyet sistemlerine dokunmayın. Bu yazılım "olduğu gibi"
> sunulur; hiçbir garanti vermez.

## Mimari

```
mercedes_coding.py   Tek tıkla başlatıcı (GUI)
Baslat.bat           Windows çift-tık başlatıcı
src/
  j2534.py     OpenPort 2.0 J2534 sarmalayıcısı (ISO15765 / CAN)
  uds.py       UDS (ISO 14229) + KWP2000 istemcisi + DTC çözümleme
  security.py  Seed/key (27) çerçevesi: XOR/Add/LFSR örnekleri + DLL köprüsü
  cbf.py       CBF tarayıcı + tanım modeli (block/field/feature/routine)
  library.py   Tüm platform tanımlarını yükleyen kütüphane + VIN eşleştirme
  coding.py    Motor: oku/yedekle/yaz/doğrula, özellik uygula, arıza, tanıtma
  cli.py       Komut satırı arayüzü
  app.py       Tkinter GUI (Özellikler / Arıza-Tanıtma / Gelişmiş)
defs/platforms/
  w176_*.json w177_*.json w205_*.json w213_*.json w222_*.json
               Her platform için gösterge/konfor/far/EZS beyinleri
tests/         Donanımsız çalışan 31 birim testi (sahte ECU)
```

## CBF Tanı & Eşleştir (kendi dosyalarınla)

Kendi CBF dosyalarını bir klasöre koy; uygulama hepsini **otomatik tanır**
(gerçek beyin adı, versiyon, desteklenen Baumuster) ve araca bağlanıp beynin
kimliğini **okuyarak** (parça no, yazılım, VIN — sadece okuma) doğru CBF'i
sıralar.

```bash
python -m src.cli index /klasor/cbf        # dosyaları tanı/listele
python -m src.cli match /klasor/cbf --ecu W204_IC --hint SAM   # araçla eşleştir
```
GUI'de **"CBF Eşleştir"** sekmesi: klasör seç → "Araçtan Oku & Eşleştir".
Aynı beynin iki versiyonu varsa (ör. iki IC_204), aracın yazılım sürümüne en
yakın olanı öne çıkarır. Son sürüm teyidini kullanıcı verir.

## Kavramlar

- **Beyin (ECU) tanımı:** bir beynin CAN ID'leri, seedkey seviyesi, kodlama
  blokları, hazır **özellikleri** ve **tanıtma rutinleri**. Her JSON bir beyin.
- **Özellik (feature):** tek tıkla uygulanan hazır ayar (örn. AMG menü =
  gösterge bloğundaki birkaç biti açar).
- **Tanıtma (routine):** RoutineControl (0x31) ile çalışan teach-in /
  kalibrasyon (örn. far beyni değişimi sonrası tanıtma).

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
