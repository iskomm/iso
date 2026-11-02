// Kangoo 2 -> BMW E70 KOMBI CAN çevirici — ESP32
//
//  Kangoo CAN (500 kbps)  --SN65HVD230--  ESP32 TWAI
//  BMW K-CAN  (100 kbps)  --MCP2515-----  ESP32 SPI
//
// Gerekli kütüphane: "autowp-mcp2515" (Arduino Kütüphane Yöneticisi'nden)
// Seri monitör: 115200 baud, satır sonu "Newline". Komutlar için "help".
//
// Ayarlar: config.h (pinler), kangoo.h (Kangoo ID'leri), bmw.h (BMW mesajları)

#include <Arduino.h>
#include <SPI.h>
#include <mcp2515.h>
#include <EEPROM.h>
#include "driver/twai.h"

#include "config.h"
#include "kangoo.h"
#include "bmw.h"
#include "demo.h"

static MCP2515 mcp(BMW_CS_PIN, BMW_SPI_HZ);
#if BMW_PTCAN_ENABLED
static MCP2515 ptcan(BMW_PTCAN_CS, BMW_SPI_HZ);
#endif
static VehicleState st;

static bool     bench = false;          // true: değerler seri monitörden gelir
static bool     twaiNormal = false;     // false: sadece dinleme
static uint32_t framesSinceStart = 0;
static uint32_t lastRx = 0;
static uint32_t rxTotal = 0, txOk = 0, txErr = 0, obdTx = 0;
#if BMW_PTCAN_ENABLED
static uint32_t ptOk = 0;
#endif
static uint16_t bmwKbps = 100;          // K-CAN normalde 100 kbps; "bmwkbps" ile denenebilir
static uint32_t lastObd = 0, lastStatus = 0, lastFuel = 0;
static bool     wasOn = false;
static uint8_t  busOffCount = 0;        // 3 kez bus-off olursa OBD sorgusu kapanır

// ---------------------------------------------------------------------------
//  Kangoo CAN (TWAI)
// ---------------------------------------------------------------------------
static bool kangooStart(bool normal) {
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(
      KANGOO_CAN_TX, KANGOO_CAN_RX, normal ? TWAI_MODE_NORMAL : TWAI_MODE_LISTEN_ONLY);
  g.rx_queue_len = 64;
  g.tx_queue_len = 4;
  twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  if (twai_driver_install(&g, &t, &f) != ESP_OK) return false;
  if (twai_start() != ESP_OK) {
    twai_driver_uninstall();
    return false;
  }
  twaiNormal = normal;
  framesSinceStart = 0;
  return true;
}

static void kangooStop() {
  twai_stop();              // bus-off durumunda hata döner, sorun değil
  twai_driver_uninstall();
}

static void kangooRestart(bool normal) {
  kangooStop();
  if (!kangooStart(normal)) Serial.println(F("! Kangoo CAN başlatılamadı"));
  else Serial.printf("> Kangoo CAN: %s\n", normal ? "normal mod (OBD sorgusu açık)" : "sadece dinleme");
}

static void kangooReceive(uint32_t now) {
  twai_message_t m;
  while (twai_receive(&m, 0) == ESP_OK) {
    rxTotal++;
    framesSinceStart++;
    lastRx = now;
    if (!bench) decodeKangooFrame(m, st);
  }
}

// Hata sayaçlarını izler; bus-off olursa güvenli tarafa (dinleme) döner.
static void kangooCheckHealth() {
  twai_status_info_t s;
  if (twai_get_status_info(&s) != ESP_OK) return;
  if (s.state == TWAI_STATE_BUS_OFF || s.state == TWAI_STATE_STOPPED) {
    busOffCount++;
    Serial.println(F("! Kangoo CAN bus-off, dinleme moduna dönülüyor"));
    kangooRestart(false);
  }
}

// ---------------------------------------------------------------------------
//  BMW K-CAN (MCP2515)
// ---------------------------------------------------------------------------
// MCP2515'in 3 gönderim tamponu var. Doluysa false döner; çağıran taraf
// mesajı kaybetmeden bir sonraki döngüde tekrar dener.
static bool bmwSend(const struct can_frame &f) {
  if (mcp.sendMessage(&f) == MCP2515::ERROR_OK) {
    txOk++;
#if BMW_PTCAN_ENABLED
    if (ptcan.sendMessage(&f) == MCP2515::ERROR_OK) ptOk++;
#endif
    return true;
  }
  txErr++;   // tampon dolu ya da gösterge ACK vermiyor
  return false;
}

// MCP2515'i iç geri döngü (loopback) moduna alıp bir çerçeve gönderir ve geri
// okur. Gösterge bağlı olmasa da ESP32 <-> MCP2515 bağlantısını doğrular.
static bool bmwSelfTest() {
  mcp.reset();
  mcp.setBitrate(bmwKbps == 500 ? CAN_500KBPS : CAN_100KBPS, BMW_MCP_CLOCK);
  mcp.setLoopbackMode();
  struct can_frame f = {};
  f.can_id = 0x123;
  f.can_dlc = 2;
  f.data[0] = 0xAB;
  f.data[1] = 0xCD;
  bool ok = mcp.sendMessage(&f) == MCP2515::ERROR_OK;
  bool got = false;
  for (int i = 0; ok && i < 50 && !got; i++) {
    struct can_frame r;
    if (mcp.readMessage(&r) == MCP2515::ERROR_OK)
      got = r.can_id == 0x123 && r.can_dlc == 2 && r.data[0] == 0xAB && r.data[1] == 0xCD;
    else
      delay(1);
  }
  mcp.setNormalMode();
  Serial.println(got ? F("> MCP2515 testi: TAMAM (ESP32 <-> MCP2515 bağlantısı çalışıyor)")
                     : F("! MCP2515 testi: BAŞARISIZ (SPI kabloları, besleme, seviye dönüştürücü, kristal)"));
  return got;
}

static void bmwSendSlots(uint32_t now) {
  for (int i = 0; i < S_TOTAL; i++) {
    Slot &s = slots[i];
    if (!s.enabled || s.id == 0 || s.periodMs == 0) continue;
    uint32_t dt = now - s.last;
    if (dt < s.periodMs) continue;
    if (dt > 1000) dt = s.periodMs;
    // buildSlot sayaçları ilerletir; gönderilemezse geri alınır
    float sd = speedDist;
    uint16_t tk = speedTick;
    uint8_t ac = aliveCnt, bc = airbagCnt, dc = dscCnt;
    if (i < S_STD_COUNT) buildSlot(i, st, dt);
    struct can_frame f;
    f.can_id = s.id;
    f.can_dlc = s.dlc;
    memcpy(f.data, s.data, 8);
    if (!bmwSend(f)) {
      speedDist = sd;
      speedTick = tk;
      aliveCnt = ac;
      airbagCnt = bc;
      dscCnt = dc;
      return;   // tamponlar dolu: kalanlar bir sonraki döngüde
    }
    s.last = now;
  }
}

struct CcLamp {
  const char *name;
  bool *flag;
  uint16_t *num;
  bool prev;
  uint32_t last;
};

static CcLamp lamps[] = {
  {"aku",    &st.warnBattery, &ccBattery, false, 0},
  {"yag",    &st.warnOil,     &ccOil,     false, 0},
  {"motor",  &st.warnEngine,  &ccEngine,  false, 0},
  {"abs",    &st.warnAbs,     &ccAbs,     false, 0},
  {"airbag", &st.warnAirbag,  &ccAirbag,  false, 0},
  {"fren",   &st.warnBrake,   &ccBrake,   false, 0},
};

static void bmwSendCheckControl(uint32_t now) {
  for (auto &l : lamps) {
    if (*l.num == 0) continue;
    bool on = *l.flag;
    if (on != l.prev || (on && now - l.last > 2000)) {
      struct can_frame f;
      fillCheckControl(f, *l.num, on);
      if (!bmwSend(f)) return;
      l.prev = on;
      l.last = now;
    }
  }
}

// Check Control taraması: numaraları sırayla yakar. Hangi numaranın hangi
// lambayı yaktığını ya da gong (uyarı sesi) çaldığını bulmak için.
static uint16_t scanCur = 0, scanEnd = 0, scanOff = 0;
static bool     scanOnPending = false;
static uint32_t scanNext = 0;
#define SCAN_STEP_MS 2500

// Gönderim tamponu doluysa mesaj kaybolmasın diye "söndür" ve "yak" ayrı
// ayrı bekletilir, gönderilene kadar her döngüde tekrar denenir.
static void ccScanUpdate(uint32_t now) {
  struct can_frame f;
  if (scanOff) {
    fillCheckControl(f, scanOff, false);
    if (!bmwSend(f)) return;
    scanOff = 0;
  }
  if (!scanCur) return;
  if (scanOnPending) {
    fillCheckControl(f, scanCur, true);
    if (!bmwSend(f)) return;
    scanOnPending = false;
    scanNext = now + SCAN_STEP_MS;
    Serial.printf("> CC %u\n", scanCur);
    return;
  }
  if ((int32_t)(now - scanNext) < 0) return;
  scanOff = scanCur;
  if (++scanCur > scanEnd) {
    Serial.println(F("> CC taraması bitti"));
    scanCur = 0;
    return;
  }
  scanOnPending = true;
}

// Devir taraması: devir değerini farklı ID / bayt konumu / ölçek / bayt sırası
// kombinasyonlarında sırayla dener. Devir 1000-4000 arasında gidip gelir;
// ibre oynadığında ekrandaki deneme numarasını not edin.
#define RPMSCAN_STEP_MS 3000
static uint8_t  rpmScan = 0;          // 0 = kapalı, yoksa 1..RPMSCAN_COUNT
static bool     rpmScanHold = false;
static uint32_t rpmScanStart = 0, rpmScanLastTx = 0;

// Seçilen devir denemesi EEPROM'da saklanır: [0] = 0xA5 işaret, [1] = deneme no
#define EE_MAGIC 0xA5

static void rpmSelApply(uint8_t n) {
  rpmSel = n <= RPMSCAN_COUNT ? n : 0;
  slots[S_RPM].id = rpmSel ? rpmVariant(rpmSel).id : 0x0AA;
}

static void rpmSelSave() {
  EEPROM.write(0, EE_MAGIC);
  EEPROM.write(1, rpmSel);
  EEPROM.commit();
}

static void rpmSelLoad() {
  if (EEPROM.read(0) == EE_MAGIC) rpmSelApply(EEPROM.read(1));
}

static void rpmScanPrint() {
  RpmVariant v = rpmVariant(rpmScan);
  Serial.printf("> Devir denemesi %u/%u: ID %03X, bayt %u-%u, %s, %s\n", rpmScan, RPMSCAN_COUNT,
     v.id, v.off, v.off + 1, v.x4 ? "x4" : "x1", v.be ? "büyük uç (BE)" : "küçük uç (LE)");
}

static void rpmScanStop() {
  if (!rpmScan) return;
  Serial.printf("> Devir taraması durdu (son deneme: %u)\n", rpmScan);
  rpmScan = 0;
  slots[S_RPM].enabled = true;
}

static void rpmScanUpdate(uint32_t now) {
  if (!rpmScan) return;
  if (!rpmScanHold && now - rpmScanStart >= RPMSCAN_STEP_MS) {
    if (++rpmScan > RPMSCAN_COUNT) {
      Serial.println(F("> Devir taraması bitti"));
      rpmScan = 0;
      slots[S_RPM].enabled = true;
      return;
    }
    rpmScanStart = now;
    rpmScanPrint();
  }
  if (now - rpmScanLastTx < 20) return;
  rpmScanLastTx = now;
  RpmVariant v = rpmVariant(rpmScan);
  uint16_t rpm = 1000 + (uint16_t)(((now - rpmScanStart) % 2000) * 3 / 2);
  struct can_frame f;
  f.can_id = v.id;
  f.can_dlc = 8;
  putRpm(f.data, v, rpm);
  bmwSend(f);
}

static void playGong() {
  if (!ccGong) {
    Serial.println(F("! Gong numarası bmw.h'da 0. 'ccscan 1 300' ile gong çalan numarayı bulun"));
    return;
  }
  struct can_frame f;
  fillCheckControl(f, ccGong, true);
  bmwSend(f);
}

// ---------------------------------------------------------------------------
//  Seri komutlar
// ---------------------------------------------------------------------------
static void printHelp() {
  Serial.println(F(
    "\nKomutlar (sayılar onluk, ID ve baytlar onaltılık):\n"
    "  help              bu yardım\n"
    "  st                durum ve sayaçlar\n"
    "  test              MCP2515 bağlantı testi (gösterge gerekmez)\n"
    "  bench 1|0         masa modu: değerleri buradan verirsiniz (araç gerekmez)\n"
    "  ign 1|0           kontak (masa modunda)\n"
    "  rpm 3000          devir        spd 80    hız km/h\n"
    "  tmp 90            motor suyu   fuel 50   yakıt %\n"
    "  sol 1|0  sag 1|0  sinyaller    park 1|0  kisa 1|0  uzun 1|0  onsis 1|0  arkasis 1|0\n"
    "  elfren 1|0        el freni\n"
    "  uyari aku|yag|motor|abs|airbag|fren 1|0\n"
    "  cc 34 1|0         Check Control numarasını doğrudan dene (onluk)\n"
    "  raw 130 45 42 69 8F E2         tek seferlik çerçeve gönder\n"
    "  rep 3B4 100 00 01 02           100 ms'de bir tekrarla  (rep 3B4 0 = sil)\n"
    "  off 1D0 / on 1D0  standart bir mesajı kapat/aç\n"
    "  demo 1|0          test modu: trafikteymiş gibi sürüş (masa modunu açar)\n"
    "  ccscan 1 300      Check Control numaralarını 2.5 sn arayla sırayla dene (ccscan 0 = dur)\n"
    "  gong              uyarı sesini çal (bmw.h'daki ccGong numarası)\n"
    "  per 0AA 10        standart bir mesajın gönderim aralığını değiştir (ms)\n"
    "  rpmfmt 0|1|2      devir mesajının biçimini değiştir (bkz. bmw.h)\n"
    "  devirscan         devir mesajı için 112 farklı biçimi sırayla dene (3 sn arayla)\n"
    "  devirsec 17       ibreyi oynatan denemeyi seç ve kalıcı kaydet (devirsec 0 = standart)\n"
    "  bmwkbps 100|500   BMW tarafının hızı (K-CAN 100, PT-CAN 500)\n"
    "  cal 1.25          hız kalibrasyonu (şu anki değeri st ile görün)\n"
    "  fcal 0000 1F40    yakıt ham değerleri: boş dolu (onaltılık)\n"));
}

static void printStatus() {
  Serial.printf("\nMod: %s | Kangoo CAN: %s | hat %s\n",
                bench ? "MASA" : "ARAÇ",
                twaiNormal ? "normal" : "dinleme",
                (millis() - lastRx < BUS_TIMEOUT_MS) ? "aktif" : "sessiz");
  Serial.printf("Kontak: %s  Devir: %.0f  Hız: %.1f  Su: %d°C  Yakıt: %.0f%%\n",
                st.ignitionOn ? "açık" : "kapalı", st.rpm, st.speedKmh, st.coolantC, st.fuelPct);
  Serial.printf("Sinyal sol/sağ: %d/%d  Park: %d  Kısa/uzun: %d/%d  Sis ön/arka: %d/%d  El freni: %d\n",
                st.turnLeft, st.turnRight, st.parkLights, st.lowBeam, st.highBeam, st.frontFog, st.rearFog, st.handbrake);
  Serial.printf("Uyarı akü/yağ/motor/abs/airbag/fren: %d/%d/%d/%d/%d/%d\n",
                st.warnBattery, st.warnOil, st.warnEngine, st.warnAbs, st.warnAirbag, st.warnBrake);
  Serial.printf("Kangoo alınan: %lu  OBD istek: %lu\n", (unsigned long)rxTotal, (unsigned long)obdTx);
  if (rpmSel) Serial.printf("Devir mesajı: deneme %u (ID %03X)\n", rpmSel, slots[S_RPM].id);
  else Serial.printf("Devir mesajı: standart, rpmfmt %u\n", rpmFormat);
  // "tampon dolu" hata değildir: mesaj bir sonraki döngüde tekrar gönderilir.
  // TEC (gönderim hata sayacı) 0'a yakınsa gösterge mesajları alıyor (ACK veriyor);
  // 128 ve üstü ise kimse almıyor: kablolar, hız ya da kristal yanlış.
  Serial.printf("BMW K-CAN (%u kbps) gönderilen: %lu  tampon dolu: %lu  TEC: %u\n",
     bmwKbps, (unsigned long)txOk, (unsigned long)txErr, mcp.errorCountTX());
#if BMW_PTCAN_ENABLED
  Serial.printf("BMW PT-CAN gönderilen: %lu  TEC: %u\n", (unsigned long)ptOk, ptcan.errorCountTX());
#endif
  Serial.printf("Hız kalibrasyonu: %.3f  Yakıt boş/dolu: %04X/%04X\n", speedScale, fuelRawEmpty, fuelRawFull);
  Serial.print("Açık mesajlar:");
  for (int i = 0; i < S_TOTAL; i++)
    if (slots[i].enabled && slots[i].id) Serial.printf(" %03X", slots[i].id);
  Serial.println();
}

static int parseBytes(char **tokens, int count, uint8_t *out) {
  int n = 0;
  for (; n < count && n < 8; n++) out[n] = (uint8_t)strtoul(tokens[n], nullptr, 16);
  return n;
}

static int findStdSlot(uint16_t id) {
  for (int i = 0; i < S_STD_COUNT; i++)
    if (slots[i].id == id) return i;
  return -1;
}

static bool setFlag(const char *name, bool v) {
  struct { const char *n; bool *f; } map[] = {
    {"sol", &st.turnLeft}, {"sag", &st.turnRight}, {"park", &st.parkLights}, {"kisa", &st.lowBeam},
    {"uzun", &st.highBeam}, {"onsis", &st.frontFog}, {"arkasis", &st.rearFog},
    {"elfren", &st.handbrake}, {"ign", &st.ignitionOn},
  };
  for (auto &e : map) {
    if (!strcmp(name, e.n)) { *e.f = v; return true; }
  }
  return false;
}

// Elle değer verilince: test modu açıksa kapatılır (yoksa değeri hemen ezer),
// masa modu kapalıysa uyarılır.
static void manualValue() {
  if (demo.on) {
    demo.on = false;
    Serial.println(F("> Test modu kapatıldı (elle değer verildi)"));
  }
  if (!bench) Serial.println(F("! Masa modu kapalı: göstergeye gitmesi için önce 'bench 1' yazın"));
}

static void handleCommand(char *line) {
  char *argv[12];
  int argc = 0;
  for (char *tok = strtok(line, " "); tok && argc < 12; tok = strtok(nullptr, " "))
    argv[argc++] = tok;
  if (!argc) return;
  const char *cmd = argv[0];
  const char *a1 = argc > 1 ? argv[1] : nullptr;
  const char *a2 = argc > 2 ? argv[2] : nullptr;

  if (!strcmp(cmd, "help") || !strcmp(cmd, "?")) { printHelp(); return; }
  if (!strcmp(cmd, "st")) { printStatus(); return; }
  if (!strcmp(cmd, "test")) { bmwSelfTest(); return; }

  if (!strcmp(cmd, "demo") && a1) {
    if (atoi(a1)) {
      bench = true;
      demoStart(st, millis());
      Serial.println(F("> Test modu: trafik taklidi başladı (durdurmak için demo 0)"));
    } else {
      demo.on = false;
      st.rpm = st.speedKmh = 0;
      st.turnLeft = st.turnRight = false;
      Serial.println(F("> Test modu kapandı"));
    }
    return;
  }
  if (!strcmp(cmd, "ccscan") && a1) {
    if (scanCur && !scanOnPending) scanOff = scanCur;   // yanık kalanı söndür
    scanCur = atoi(a1);
    scanEnd = a2 ? atoi(a2) : scanCur + 100;
    scanOnPending = scanCur != 0;
    if (scanCur) Serial.println(F("> Tarama: numara ekranda yazarken göstergeye bakın, sesi dinleyin"));
    else Serial.println(F("> Tarama durdu"));
    return;
  }
  if (!strcmp(cmd, "devirsec") && a1) {
    rpmScanStop();
    rpmSelApply(atoi(a1));
    rpmSelSave();
    if (rpmSel) {
      rpmScan = rpmSel;      // açıklamayı yazdırmak için
      Serial.print(F("> Seçildi ve kaydedildi. "));
      rpmScanPrint();
      rpmScan = 0;
    } else {
      Serial.printf("> Devir: standart biçim (rpmfmt %u), kaydedildi\n", rpmFormat);
    }
    return;
  }
  if (!strcmp(cmd, "devirscan")) {
    if (a1 && !strcmp(a1, "tut")) {
      rpmScanHold = !rpmScanHold;
      Serial.println(rpmScanHold ? F("> Devir taraması bu denemede bekliyor ('devirscan tut' = devam)")
                                 : F("> Devir taraması devam ediyor"));
      return;
    }
    int n = a1 ? atoi(a1) : 1;
    if (n <= 0) { rpmScanStop(); return; }
    manualValue();
    rpmScan = n > RPMSCAN_COUNT ? RPMSCAN_COUNT : n;
    rpmScanHold = false;
    rpmScanStart = millis();
    slots[S_RPM].enabled = false;     // standart devir mesajı karışmasın
    Serial.println(F("> Devir taraması: ibre oynayınca deneme numarasını not edin"));
    Serial.println(F("  devirscan tut = bu denemede bekle, devirscan 0 = durdur, devirscan 25 = 25'ten başla"));
    rpmScanPrint();
    return;
  }
  if (!strcmp(cmd, "gong")) { playGong(); return; }
  if (!strcmp(cmd, "bmwkbps") && a1) {
    bmwKbps = atoi(a1) == 500 ? 500 : 100;
    bmwSelfTest();
    Serial.printf("> BMW tarafı %u kbps\n", bmwKbps);
    return;
  }
  if (!strcmp(cmd, "per") && a2) {
    int i = findStdSlot(strtoul(a1, nullptr, 16));
    if (i < 0) { Serial.println(F("? Standart mesaj değil")); return; }
    slots[i].periodMs = atoi(a2);
    Serial.printf("> %03X her %u ms\n", slots[i].id, slots[i].periodMs);
    return;
  }
  if (!strcmp(cmd, "rpmfmt") && a1) {
    rpmFormat = atoi(a1) % 3;
    Serial.printf("> Devir biçimi %u\n", rpmFormat);
    return;
  }
  if (!strcmp(cmd, "bench") && a1) {
    demo.on = false;
    bench = atoi(a1);
    if (bench) { st = VehicleState(); st.ignitionOn = true; }
    Serial.printf("> Masa modu %s\n", bench ? "AÇIK (kontak açık)" : "kapalı");
    return;
  }
  if (!strcmp(cmd, "rpm") && a1) {
    manualValue();
    st.rpm = atof(a1);
    Serial.print(F("> Devir "));
    Serial.println(st.rpm, 0);
    return;
  }
  if (!strcmp(cmd, "spd") && a1) {
    manualValue();
    st.speedKmh = atof(a1);
    Serial.print(F("> Hız "));
    Serial.println(st.speedKmh, 0);
    return;
  }
  if (!strcmp(cmd, "tmp") && a1) {
    manualValue();
    st.coolantC = atoi(a1);
    Serial.printf("> Motor suyu %d C\n", st.coolantC);
    return;
  }
  if (!strcmp(cmd, "fuel") && a1) {
    manualValue();
    st.fuelPct = atof(a1);
    Serial.print(F("> Yakıt %"));
    Serial.println(st.fuelPct, 0);
    return;
  }
  if (a1 && setFlag(cmd, atoi(a1))) {
    if (strcmp(cmd, "ign")) manualValue();
    Serial.printf("> %s %s\n", cmd, atoi(a1) ? "açık" : "kapalı");
    return;
  }

  if (!strcmp(cmd, "uyari") && a2) {
    for (auto &l : lamps) {
      if (!strcmp(a1, l.name)) {
        *l.flag = atoi(a2);
        if (*l.num == 0) Serial.println(F("! Bu uyarının CC numarası bmw.h'da 0, önce 'cc' ile bulun"));
        return;
      }
    }
    Serial.println(F("? Bilinmeyen uyarı"));
    return;
  }
  if (!strcmp(cmd, "cc") && a2) {
    struct can_frame f;
    fillCheckControl(f, (uint16_t)atoi(a1), atoi(a2));
    bmwSend(f);
    Serial.printf("> CC %d %s\n", atoi(a1), atoi(a2) ? "yak" : "söndür");
    return;
  }
  if (!strcmp(cmd, "raw") && a1) {
    struct can_frame f = {};
    f.can_id = strtoul(a1, nullptr, 16);
    f.can_dlc = parseBytes(argv + 2, argc - 2, f.data);
    bmwSend(f);
    Serial.printf("> %03lX gönderildi (%d bayt)\n", (unsigned long)f.can_id, f.can_dlc);
    return;
  }
  if (!strcmp(cmd, "rep") && a2) {
    uint16_t id = strtoul(a1, nullptr, 16);
    uint16_t period = atoi(a2);
    int std = findStdSlot(id);
    if (std >= 0 && period) {
      slots[std].enabled = false;
      Serial.printf("> Standart %03X kapatıldı, yerine sizinki gönderilecek\n", id);
    }
    int freeIdx = -1;
    for (int i = S_CUSTOM_FIRST; i < S_TOTAL; i++) {
      if (slots[i].id == id) { freeIdx = i; break; }
      if (slots[i].id == 0 && freeIdx < 0) freeIdx = i;
    }
    if (freeIdx < 0) { Serial.println(F("! Boş yuva yok")); return; }
    Slot &s = slots[freeIdx];
    s = Slot();
    if (!period) {
      if (std >= 0) slots[std].enabled = true;
      Serial.printf("> %03X tekrarı silindi\n", id);
      return;
    }
    s.id = id;
    s.periodMs = period;
    s.dlc = parseBytes(argv + 3, argc - 3, s.data);
    s.enabled = true;
    Serial.printf("> %03X her %u ms (%d bayt)\n", id, period, s.dlc);
    return;
  }
  if ((!strcmp(cmd, "off") || !strcmp(cmd, "on")) && a1) {
    int i = findStdSlot(strtoul(a1, nullptr, 16));
    if (i < 0) { Serial.println(F("? Standart mesaj değil")); return; }
    slots[i].enabled = !strcmp(cmd, "on");
    Serial.printf("> %03X %s\n", slots[i].id, slots[i].enabled ? "açık" : "kapalı");
    return;
  }
  if (!strcmp(cmd, "cal") && a1) { speedScale = atof(a1); Serial.printf("> Hız kalibrasyonu %.3f\n", speedScale); return; }
  if (!strcmp(cmd, "fcal") && a2) {
    fuelRawEmpty = strtoul(a1, nullptr, 16);
    fuelRawFull = strtoul(a2, nullptr, 16);
    Serial.printf("> Yakıt boş/dolu %04X/%04X\n", fuelRawEmpty, fuelRawFull);
    return;
  }
  Serial.println(F("? Bilinmeyen komut, 'help' yazın"));
}

static void readSerial() {
  static char buf[128];
  static uint8_t len = 0;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      buf[len] = 0;
      if (len) handleCommand(buf);
      len = 0;
    } else if (len < sizeof(buf) - 1) {
      buf[len++] = ch;
    }
  }
}

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("\nKangoo -> E70 KOMBI çevirici"));
  EEPROM.begin(16);
  rpmSelLoad();

  SPI.begin();
  bmwSelfTest();   // sonunda normal moda geçer
#if BMW_PTCAN_ENABLED
  ptcan.reset();
  if (ptcan.setBitrate(CAN_500KBPS, BMW_PTCAN_CLOCK) == MCP2515::ERROR_OK && ptcan.setNormalMode() == MCP2515::ERROR_OK)
    Serial.println(F("> BMW PT-CAN MCP2515 hazır (500 kbps)"));
  else
    Serial.println(F("! BMW PT-CAN MCP2515 bulunamadı"));
#endif

  // Her zaman önce sadece dinleme: hız yanlışsa araç hattını bozmamak için.
  if (!kangooStart(false)) Serial.println(F("! Kangoo CAN başlatılamadı"));

#if USE_FUEL_ADC
  analogReadResolution(12);
#endif
  printHelp();
}

void loop() {
  uint32_t now = millis();
  readSerial();
  kangooReceive(now);

  bool busAlive = rxTotal > 0 && (now - lastRx < BUS_TIMEOUT_MS);

#if USE_OBD_POLLING
  // Hattan yeterince düzgün mesaj geldiyse hız doğrudur, normal moda geç.
  if (!twaiNormal && busOffCount < 3 && framesSinceStart >= FRAMES_BEFORE_TX) kangooRestart(true);
  if (twaiNormal && !bench && busAlive && now - lastObd >= OBD_PERIOD_MS) {
    lastObd = now;
    if (obdSendNext()) obdTx++;
  }
#endif

#if USE_FUEL_ADC
  if (!bench && now - lastFuel >= 100) {
    lastFuel = now;
    float pct = 100.0f * (analogRead(FUEL_ADC_PIN) - FUEL_ADC_EMPTY) / (float)(FUEL_ADC_FULL - FUEL_ADC_EMPTY);
    pct = constrain(pct, 0.0f, 100.0f);
    st.fuelPct = st.fuelPct * 0.98f + pct * 0.02f;   // depodaki çalkalanmayı yumuşat
  }
#endif

  if (now - lastStatus >= 500) {
    lastStatus = now;
    kangooCheckHealth();
  }

  if (!bench) st.ignitionOn = busAlive;
  demoUpdate(st, now);
  updateTurn(st, now);
  if (st.ignitionOn) {
    bmwSendSlots(now);
    bmwSendCheckControl(now);
    ccScanUpdate(now);
    rpmScanUpdate(now);
  } else if (wasOn) {
    st.rpm = 0;
    st.speedKmh = 0;
    Serial.println(F("> Kontak kapalı, gösterge uyuyacak"));
  }
  wasOn = st.ignitionOn;
}
