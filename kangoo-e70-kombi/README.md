# Kangoo 2 (2011, 1.5 dCi) → BMW E70 X5 göstergesi (KOMBI) — CAN çevirici

Kangoo'nun CAN hattındaki bilgileri (devir, hız, sıcaklık, sinyaller, uyarılar)
okuyup BMW E70 göstergesinin anladığı K-CAN mesajlarına çeviren proje.
İki sürümü var: **Arduino Nano / Uno** (aşağıda) ve **ESP32** (devamında).

```
 Kangoo CAN (500 kbps)                                BMW E70 KOMBI
 OBD pin 6 / 14   ──► SN65HVD230 ──► ESP32 ──► MCP2515 ──► K-CAN (100 kbps)
                       (dinleme)     TWAI       SPI
```

| Klasör | Ne işe yarar |
|---|---|
| `nano_sniffer/` | **Nano/Uno:** Kangoo hattını **sadece dinler**. Hangi ID'de hangi bilgi var, onu bulmak için |
| `nano_gateway/` | **Nano/Uno:** Asıl çevirici. Masada gösterge testi için komutlar da içerir |
| `sniffer/` | ESP32 sürümü (sniffer) |
| `gateway/` | ESP32 sürümü (çevirici) |

---

## Arduino Nano / Uno sürümü

Nano 5V ile çalıştığı için MCP2515 modülleri **doğrudan** bağlanır, seviye dönüştürücü
gerekmez. Kangoo ve BMW tarafı için **iki MCP2515** kullanılır, ikisi aynı SPI hattını
paylaşır, sadece CS pinleri ayrıdır. Uno'da pinler aynıdır.

```
 Kangoo CAN (500k) ── MCP2515 #1 (CS=D9)  ──┐
                                            ├── D11 / D12 / D13 ── Nano
 BMW K-CAN  (100k) ── MCP2515 #2 (CS=D10) ──┘
```

### Nano ↔ MCP2515 bağlantıları
| MCP2515 pini | BMW modülü (#2) | Kangoo modülü (#1) |
|---|---|---|
| VCC | 5V | 5V |
| GND | GND | GND |
| CS | **D10** | **D9** |
| SO | D12 | D12 (ortak) |
| SI | D11 | D11 (ortak) |
| SCK | D13 | D13 (ortak) |
| INT | boş | boş |
| CANH / CANL | E70 K-CAN H / L | OBD pin 6 / pin 14 |
| 120 Ω jumper | **takılı** (açık, haberleşme olmazsa çıkarıp deneyin) | **çıkarın** (araç hattı zaten sonlandırılmış) |

- Masa testi için sadece **BMW modülü (#2)** yeterli. `nano_gateway/config.h` içinde
  `KANGOO_ENABLED` değerini **0** yapın, araca geçerken tekrar **1** yapın.
- Sniffer (`nano_sniffer`) **tek** MCP2515 ile çalışır, CS = **D10**. Kangoo'yu dinlerken
  BMW modülünü sökmeden, Kangoo modülünü D10'a takarak da kullanabilirsiniz.
- Kristal 16 MHz ise `config.h`'daki `BMW_MCP_CLOCK` / `KANGOO_MCP_CLOCK` (sniffer'da `MCP_CLOCK`) değerini `MCP_16MHZ` yapın.
- Arduino IDE: kart **Arduino Nano**, işlemci **ATmega328P**. Yükleme hata verirse
  **ATmega328P (Old Bootloader)** seçin (klon Nano'larda çoğu zaman bu gerekir).
- Seri monitör: gateway **115200**, sniffer **115200** baud.

### Nano besleme (araçta)
Aracın 12V'u 14.4V'a kadar çıkar ve dalgalanır. Nano'nun kendi regülatörü bunda çok ısınır.
**12V → 5V DC-DC çevirici** kullanıp çıkışını Nano'nun **5V** pinine verin. MCP2515'ler de
aynı 5V'tan beslenir. Masada USB kablosu yeterli.

Kalan adımlar (gösterge pinleri, masa testi komutları, sniffer kullanımı) iki sürümde aynıdır.
Aşağıdaki ESP32 bağlantı bölümünü atlayabilirsiniz.

---

## ⚠️ Başlamadan önce

1. **Orijinal Kangoo göstergesini sökmeyin.** Torpidonun arkasında bağlı kalsın.
   Yakıt şamandırası, uyarı sesi ve diğer modüllerle haberleşme ona bağlı olabilir.
   BMW göstergesi sadece **ekran** görevi görecek.
2. **Kilometre:** BMW göstergesi kendi kilometresini gösterir. Muayenede gerçek km
   kayıtla karşılaştırılıyor. Göstergede aracın **gerçek kilometresi** görünmeli.
   Gerekirse göstergenin kilometresini yetkili bir yerde aracın gerçek değerine ayarlatın.
3. **Uyarı lambaları:** ABS, airbag, fren ve motor arıza lambaları muayenede kontrol
   ediliyor. Bunlar BMW göstergesinde doğru yanmıyorsa orijinal gösterge görünür kalmalı.
4. Bu projedeki BMW mesaj biçimleri **E90 gösterge projelerinden** bilinen değerler,
   Kangoo ID'leri de **aday** değerler. İkisi de sizin parçalarınızda test edilerek
   doğrulanacak. Adımlar aşağıda.

---

## Malzeme listesi

| Parça | Adet | Not |
|---|---|---|
| ESP32 DevKit (ESP32-WROOM-32) | 1 | Klasik ESP32. C3/S3 de olur ama pinleri değiştirmeniz gerekir |
| SN65HVD230 CAN modülü (3.3V) | 1 | Kangoo tarafı |
| MCP2515 + TJA1050 CAN modülü | 1 | BMW tarafı. Kristalin üstünde yazan değeri not edin (8 ya da 16 MHz) |
| 4 kanallı seviye dönüştürücü (BSS138) | 1 | ESP32 (3.3V) ↔ MCP2515 (5V) arasında |
| 12V → 5V DC-DC çevirici (en az 1A) | 1 | Örneğin mini-360 ya da LM2596 |
| 12V 2A adaptör | 1 | Masada test için |
| Sigorta ve sigorta yuvası, 2A ve 5A | 1+1 | Araç montajı için |
| Bükümlü kablo (CAN için) | | CAN-H ve CAN-L birbirine bükülü olmalı |

---

## Bağlantı şeması

### ESP32 ↔ SN65HVD230 (Kangoo tarafı)
| ESP32 | SN65HVD230 | Araç |
|---|---|---|
| 3V3 | 3V3 | |
| GND | GND | OBD pin 4 ya da 5 (şasi) |
| GPIO25 | CTX (D) | |
| GPIO26 | CRX (R) | |
| | CANH | **OBD pin 6** |
| | CANL | **OBD pin 14** |

> ⚠️ SN65HVD230 modülünün üzerinde **120 Ω'luk bir direnç** var (genelde "R2" ya da
> "120" yazar). **Bu direnci sökün.** Aracın hattı zaten sonlandırılmış durumda,
> üçüncü bir sonlandırma hattı bozar.

### ESP32 ↔ seviye dönüştürücü ↔ MCP2515 (BMW tarafı)
| ESP32 (3.3V tarafı) | Dönüştürücü | MCP2515 (5V tarafı) |
|---|---|---|
| 3V3 | LV | |
| 5V (VIN) | HV | VCC |
| GND | GND | GND |
| GPIO18 | LV1 ↔ HV1 | SCK |
| GPIO23 | LV2 ↔ HV2 | SI |
| GPIO19 | LV3 ↔ HV3 | SO |
| GPIO4 | LV4 ↔ HV4 | CS |
| | | INT boş kalabilir |

MCP2515'in **CANH / CANL** çıkışları BMW göstergesinin K-CAN H / K-CAN L pinlerine gider.
MCP2515 modülündeki 120 Ω jumper'ı önce **takılı** bırakın. Haberleşme olmazsa çıkarıp deneyin.

### Besleme
```
 12V (kontakla gelen) ──[2A sigorta]──► DC-DC ──► 5V ──► ESP32 VIN + dönüştürücü HV + MCP2515 VCC
 12V (kontakla gelen) ──[5A sigorta]──► BMW göstergesi 12V (Kl.30) girişi
 Şasi ─────────────────────────────────► hepsinin GND'si ortak
```
> OBD soketinin **16. pini sürekli 12V**. Oradan beslerseniz araç kapalıyken aküyü bitirir.
> Kalıcı montajda **kontakla gelen 12V** kullanın (örneğin teyp ACC hattı ya da sigorta kutusu).

---

## BMW E70 göstergesinin pin bağlantıları

E70 göstergesinin çalışması için **4 bağlantı** yeterli:

| Bağlantı | Ne bağlanacak |
|---|---|
| **Kl.30** (12V sürekli) | 12V (projede kontakla gelen 12V) |
| **Kl.31** (şasi) | GND |
| **K-CAN H** | MCP2515 CANH |
| **K-CAN L** | MCP2515 CANL |

Kontak bilgisi (Kl.15) telden değil, **CAN'den 0x130 mesajıyla** geliyor. Onu ESP32 gönderiyor.

**Pin numaraları:** Göstergenin parça numarasına ve yılına göre değişebildiği için burada
kesin numara vermiyorum. Yanlış pine 12V vermek göstergeyi yakar. İki güvenilir yol var:

1. **BMW bağlantı şeması:** ISTA ya da newTIS'te E70 → *Kombi (instrument cluster)* →
   soket pin atamasına bakın. Göstergenin arkasındaki etikette yazan parça numarasını
   (örneğin `9 xxx xxx`) ve yılı bilin.
2. **Kartın üzerinden bulmak** (multimetre ile, gösterge söküldüyse):
   - Kartta CAN transceiver entegresini bulun. E serisinin K-CAN'i düşük hızlı, hataya
     dayanıklı CAN olduğu için genelde **TJA1055** ya da **TJA1054** kullanılır (entegrenin
     üstünde yazar).
   - TJA1054/1055'te **pin 12 = CANH**, **pin 11 = CANL**, **pin 14 = BAT** (12V),
     **pin 13 = GND**. Entegrede farklı bir yazı varsa önce onun datasheet'ine bakın.
   - Multimetreyi süreklilik (bip) konumuna alın, soketteki pinlerden hangisinin
     entegrenin pin 12 ve 11'ine gittiğini bulun: bunlar K-CAN H ve L.
   - 12V pini genelde bir diyot ya da koruma elemanı üzerinden besleme katına gider.
     Şasi pinleri kartın geniş bakır alanına bağlıdır.

Bulduğunuz pinleri buraya yazın:

| Gösterge soketi pin no | Görev |
|---|---|
| | Kl.30 (12V) |
| | Kl.31 (GND) |
| | K-CAN H |
| | K-CAN L |

> Göstergenin arkasının ve soketin fotoğrafını çekerseniz pinleri birlikte bulabiliriz.

---

## Yazılım kurulumu

1. **Arduino IDE 2.x** kurun.
2. *Dosya → Tercihler → Ek kart yöneticisi URL'leri* alanına şunu ekleyin:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. *Kart Yöneticisi*'nden **esp32 (Espressif Systems)** paketini kurun. Kart olarak **ESP32 Dev Module** seçin.
4. *Kütüphane Yöneticisi*'nden **autowp-mcp2515** kütüphanesini kurun (gateway için, sürüm 1.2 ya da üstü).
5. `sniffer/sniffer.ino` ya da `gateway/gateway.ino` dosyasını açıp yükleyin.

`gateway/config.h` içinde **MCP2515 kristalini** (`MCP_8MHZ` / `MCP_16MHZ`) kendi modülünüze göre ayarlayın.

---

## Adım 1 — Masada gösterge testi (araç gerekmez)

Önce BMW göstergesini masada çalıştırın. Böylece BMW tarafının doğru olduğundan emin olursunuz.

1. **Önce göstergesiz:** ESP32 ve MCP2515'i bağlayıp `gateway`'i yükleyin. Seri monitörü açın
   (**115200 baud**, satır sonu **Newline**). Açılışta `MCP2515 testi: TAMAM` yazmalı.
   Yazmıyorsa göstergeye geçmeden SPI kablolarını ve kristal ayarını düzeltin. Testi
   istediğiniz zaman `test` komutuyla tekrarlayabilirsiniz.
2. Göstergeyi 12V adaptöre (ayarlı güç kaynağı varsa akım sınırı ~1A), MCP2515'in
   CANH/CANL'ini göstergenin K-CAN H/L pinlerine bağlayın. ESP32'ye reset atın.
3. Şu komutları sırayla deneyin:
   ```
   bench 1        -> masa modu, kontak açık (gösterge uyanmalı)
   rpm 3000       -> devir ibresi
   spd 100        -> hız ibresi
   tmp 90         -> sıcaklık
   fuel 50        -> yakıt
   sol 1          -> sol sinyal
   kisa 1         -> kısa far lambası
   st             -> durum
   ```
4. Çalışmayan bir şey olursa:
   - `off 1D0` → o mesajı kapatın, `rep 1D0 200 <baytlar>` → farklı baytlar deneyin.
   - `raw <ID> <baytlar>` → tek seferlik mesaj gönderin.
   - Doğru değeri bulunca `gateway/bmw.h` içine yazıp yeniden yükleyin.
5. **Hız kalibrasyonu:** `spd 100` verin. İbre 100'ü göstermiyorsa `cal 1.2`, `cal 0.8` gibi
   değerlerle ayarlayın. Bulduğunuz değeri `bmw.h` içindeki `speedScale`'e yazın.
6. **Uyarı lambaları:** `cc 34 1` gibi komutlarla Check Control numaralarını deneyin. Hangi
   numaranın hangi lambayı yaktığını not edip `bmw.h` içindeki `ccBattery`, `ccOil` gibi
   değişkenlere yazın.

---

### Test modu, uyarı sesi ve uyarı lambaları

| Komut | Ne yapar |
|---|---|
| `demo 1` | **Trafik taklidi.** Önce ibre testi, sonra kırmızı ışık, kalk-dur, şehir içi, dönüş (sinyal + yavaşlama), çevre yolu, ara sıra sert gaz. Vites büyütür/küçültür, motor ısınır, yakıt azalır. `demo 0` ile durur |
| `rpmfmt 0` / `1` / `2` | Devir ibresi oynamıyorsa devir mesajının 3 farklı biçimini deneyin |
| `per 0AA 10` | Bir mesajın gönderim aralığını değiştirir (ms). Devir varsayılan olarak 20 ms'de bir gidiyor |
| `ccscan 1 300` | Check Control numaralarını 2.5 sn arayla sırayla yakar. Ekranda numara yazar: hangi numarada **gong çaldığını** ve hangi lambanın yandığını not edin. `ccscan 0` ile durur |
| `gong` | `bmw.h`'daki `ccGong` numarasıyla uyarı sesini çalar |
| `bmwkbps 500` | BMW tarafını 500 kbps'ye alır (PT-CAN denemesi için). `bmwkbps 100` ile K-CAN'e döner |

**Devir ibresi oynamıyorsa (PT-CAN):** BMW'de devir bilgisi aslında PT-CAN'de (500 kbps)
dolaşıyor. E70 göstergesi devri oradan okuyorsa K-CAN'e gönderilen 0x0AA işe yaramaz.
Göstergenin kartında K-CAN entegresinden (TJA1055/TJA1054) başka bir CAN entegresi
(TJA1040/1041/1042/1050/1051, 82C251 gibi) varsa o PT-CAN'dir; CANH = pin 7, CANL = pin 6.
Ayrı bir MCP2515'i o pinlere bağlayıp `config.h`'da `BMW_PTCAN_ENABLED 1` yapın
(Nano'da CS = D8; masada Kangoo modülü yokken D9'u da kullanabilirsiniz). Bütün BMW
mesajları PT-CAN'e de kopyalanır. `st` çıktısında **TEC** değeri 0'a yakınsa o hatta
mesajları alan biri var demektir; 128 ve üstü ise kimse almıyor.

**Uyarı lambalarını söndürmek ("gerçek araca bağlı" taklidi):** Gösterge ABS/DSC, airbag,
akü gibi modüllerden düzenli mesaj alamayınca uyarı yakar. Program bu modüllerin yaşam
mesajlarını da gönderir: `0x0C0` (ABS), `0x0D7` (airbag), `0x19E` (DSC), `0x3B4` (akü),
`0x2CA` (dış sıcaklık). Bunlar E90 projelerinden alınmıştır. Hangi lambanın hangi mesajla
söndüğünü görmek için `off 19E` / `on 19E` gibi komutlarla tek tek kapatıp açın.
Hâlâ yanan lambalar varsa hangileri olduğunu not edin, eksik mesajı birlikte buluruz.

> ⚠️ Araca takıldığında BMW göstergesindeki uyarılar **Kangoo'nun gerçek uyarılarını**
> göstermeli (adım 2'de sniffer ile bulunacak). Sahte "her şey yolunda" mesajları sadece
> eksik BMW modüllerinin yerini tutar, Kangoo'nun arızalarını gizlememeli.

## Adım 2 — Kangoo sinyallerini bulma (sniffer)

1. `sniffer`'ı yükleyin. ESP32 ve SN65HVD230'u OBD soketine bağlayın (pin 6, 14, 4/5).
2. Seri monitör: **921600 baud**, satır sonu **Newline**.
3. Kontağı açın. Ekrana `YENİ 186 [8] ...` gibi satırlar akmalı. Akmıyorsa `b 250` ile 250 kbps deneyin.
4. **`n`** yazın ve 5 saniye **hiçbir şeye dokunmayın**. Bu sürede sayaçlar ve titreyen
   sensörler "gürültü" olarak öğrenilir, sonra ekranda görünmez.
5. **Tek bir şey yapın** ve ekrana bakın. Örneğin sol sinyali açtığınızda:
   ```
       12.345 5DE [8]  00 [04] 00 00 ...   B1 m04 0>1
   ```
   Bu, **ID 0x5DE, bayt 1, maske 0x04** demek (örnek değer, sizinki farklı olabilir).
6. Bunu `gateway/kangoo.h` içine yazın:
   ```cpp
   static const BitSig SIG_TURN_LEFT = {0x5DE, 1, 0x04, false};
   ```
   Sinyal 1'den 0'a dönerek aktif oluyorsa son değer `true` olacak.
7. Aynısını sağ sinyal, kısa/uzun far, sis, el freni ve uyarı lambaları için tekrarlayın.

Diğer komutlar: `s` = bütün ID'lerin özeti, `f 5DE` = sadece bir ID'yi göster,
`r` = ham kayıt (candump biçimi, **SavvyCAN** programına aktarılabilir).

**Devir, hız ve sıcaklık için sniffer gerekmez:** `config.h` içinde `USE_OBD_POLLING 1`
olduğu sürece bunlar standart OBD sorgusuyla (PID 0C, 0D, 05) okunur. ESP32 önce hattı
sadece dinler, 200 düzgün mesaj gördükten sonra sorgu göndermeye başlar. Hatta sorun
olursa (bus-off) kendiliğinden dinleme moduna döner, 3 kez olursa sorguyu tamamen kapatır.

---

## Adım 3 — Araca montaj

1. Masada her şey çalıştıktan sonra ESP32'yi `gateway` ile araca bağlayın.
2. Kontağı açın, seri monitörde `st` yazın:
   - `Kangoo CAN: normal`, `hat aktif` görünmeli.
   - Devir ve sıcaklık değerleri gerçekle uyuşmalı.
3. Kontağı kapatın. 1.5 saniye sonra gösterge uyku moduna geçmeli (`Kontak kapalı` yazar).
4. Kalıcı montajda CAN kablolarını OBD soketinin arkasından ya da göstergeye giden
   CAN hattından alın. Bağlantıları lehimleyip makaronla kapatın.

---

## Sorun giderme

| Belirti | Kontrol edin |
|---|---|
| `MCP2515 bulunamadı` | SPI kabloları, seviye dönüştürücü, `config.h`'daki kristal değeri |
| Gösterge hiç uyanmıyor | 12V ve GND, K-CAN H/L yer değiştirmiş mi, 0x130 mesajı (`st` ile açık mesajlara bakın) |
| `BMW gönderilen` artmıyor, `hata` artıyor | Gösterge ACK vermiyor: CAN kabloları, 120 Ω jumper'ı çıkarıp deneyin |
| Sniffer'da hiç mesaj yok | Kontak açık mı, OBD pin 6/14 doğru mu, `b 250` deneyin |
| İbreler titriyor ya da zıplıyor | `OBD_PERIOD_MS`'yi küçültün ya da devri yayın (broadcast) ID'sinden okuyun |
| Yakıt göstergesi çalışmıyor | Kangoo'da yakıt CAN'de olmayabilir: `USE_FUEL_ADC 1` ile şamandıra gerilimini okuyun (aşağıda) |

### Yakıt seviyesini şamandıradan okuma (opsiyonel)
Şamandıra hattına **yüksek dirençli** bir gerilim bölücü bağlayın (örneğin 100 kΩ + 22 kΩ,
ortası GPIO34'e, ESP32 pinine giden gerilim 3.3V'u geçmemeli). Orijinal göstergenin ölçümünü
bozmamak için direnç değerleri yüksek olmalı. Depo boşken ve doluyken `analogRead` değerini
ölçüp `config.h`'daki `FUEL_ADC_EMPTY` / `FUEL_ADC_FULL` alanlarına yazın.
