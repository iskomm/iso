// Kangoo CAN Sniffer — ESP32 (dahili TWAI) + SN65HVD230
//
// Aracın CAN hattını SADECE DİNLER (listen-only): hiçbir mesaj göndermez,
// ACK bile vermez. Araca zarar veremez.
//
// Bağlantı:  GPIO25 -> SN65HVD230 CTX/D,  GPIO26 -> SN65HVD230 CRX/R
//            CANH -> OBD pin 6,  CANL -> OBD pin 14,  GND -> OBD pin 4/5
//
// Seri monitör: 921600 baud, satır sonu "Newline". Komutlar için "h" yazın.

#include <Arduino.h>
#include "driver/twai.h"

static const gpio_num_t CAN_TX = GPIO_NUM_25;
static const gpio_num_t CAN_RX = GPIO_NUM_26;

static const twai_timing_config_t T125  = TWAI_TIMING_CONFIG_125KBITS();
static const twai_timing_config_t T250  = TWAI_TIMING_CONFIG_250KBITS();
static const twai_timing_config_t T500  = TWAI_TIMING_CONFIG_500KBITS();
static const twai_timing_config_t T1000 = TWAI_TIMING_CONFIG_1MBITS();

enum Mode { MODE_CHANGES, MODE_RAW };

struct IdEntry {
  uint32_t id;
  bool     extd;
  uint8_t  dlc;
  uint8_t  data[8];
  uint8_t  noise[8];     // kendi kendine değişen bitler (sayaçlar vb.)
  uint32_t count;
  uint32_t countAtLastSummary;
};

static const int MAX_IDS = 160;
static IdEntry ids[MAX_IDS];
static int idCount = 0;

static Mode mode = MODE_CHANGES;
static uint32_t bitrateKbps = 500;
static bool paused = false;
static bool filterOn = false;
static uint32_t filterId = 0;
static uint32_t learnUntil = 0;     // 0 değilse gürültü öğrenme sürüyor
static uint32_t lastSummary = 0;
static uint32_t totalFrames = 0;

static bool canStart(uint32_t kbps) {
  const twai_timing_config_t *t;
  switch (kbps) {
    case 125:  t = &T125;  break;
    case 250:  t = &T250;  break;
    case 1000: t = &T1000; break;
    default:   t = &T500;  kbps = 500; break;
  }
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(CAN_TX, CAN_RX, TWAI_MODE_LISTEN_ONLY);
  g.rx_queue_len = 256;
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  if (twai_driver_install(&g, t, &f) != ESP_OK) return false;
  if (twai_start() != ESP_OK) {
    twai_driver_uninstall();
    return false;
  }
  bitrateKbps = kbps;
  return true;
}

static void canStop() {
  twai_stop();
  twai_driver_uninstall();
}

static void resetTable() {
  idCount = 0;
  totalFrames = 0;
}

static IdEntry *findOrAdd(const twai_message_t &m, bool *isNew) {
  for (int i = 0; i < idCount; i++) {
    if (ids[i].id == m.identifier && ids[i].extd == (bool)m.extd) {
      *isNew = false;
      return &ids[i];
    }
  }
  if (idCount >= MAX_IDS) return nullptr;
  IdEntry *e = &ids[idCount++];
  memset(e, 0, sizeof(*e));
  e->id = m.identifier;
  e->extd = m.extd;
  *isNew = true;
  return e;
}

static void printId(uint32_t id, bool extd) {
  Serial.printf(extd ? "%08lX" : "%03lX", (unsigned long)id);
}

static void printTime(uint32_t ms) {
  Serial.printf("%7lu.%03lu ", (unsigned long)(ms / 1000), (unsigned long)(ms % 1000));
}

// candump log biçimi: SavvyCAN ve can-utils bunu içe aktarabilir.
static void printRaw(const twai_message_t &m, uint32_t us) {
  Serial.printf("(%lu.%06lu) can0 ", (unsigned long)(us / 1000000), (unsigned long)(us % 1000000));
  printId(m.identifier, m.extd);
  Serial.print('#');
  for (int i = 0; i < m.data_length_code; i++) Serial.printf("%02X", m.data[i]);
  Serial.println();
}

// Değişen baytları [köşeli parantez] içinde gösterir, altına hangi bitin
// nasıl değiştiğini yazar. Örn: "B2 m08 0>1" = 3. bayt, maske 0x08, 0'dan 1'e.
// Bu bilgiyi doğrudan gateway/kangoo.h içindeki BitSig tanımına yazabilirsiniz.
static void printChange(const IdEntry &e, const uint8_t *oldData, uint8_t oldDlc, uint32_t ms) {
  printTime(ms);
  printId(e.id, e.extd);
  Serial.printf(" [%u] ", e.dlc);
  for (int i = 0; i < e.dlc; i++) {
    uint8_t diff = (i < oldDlc) ? ((oldData[i] ^ e.data[i]) & ~e.noise[i]) : 0xFF;
    if (diff) Serial.printf("[%02X]", e.data[i]);
    else      Serial.printf(" %02X ", e.data[i]);
  }
  Serial.print("  ");
  for (int i = 0; i < e.dlc && i < oldDlc; i++) {
    uint8_t diff = (oldData[i] ^ e.data[i]) & ~e.noise[i];
    for (int b = 7; b >= 0; b--) {
      uint8_t mask = 1 << b;
      if (diff & mask) {
        Serial.printf(" B%d m%02X %d>%d", i, mask, (oldData[i] & mask) ? 1 : 0, (e.data[i] & mask) ? 1 : 0);
      }
    }
  }
  Serial.println();
}

static int cmpId(const void *a, const void *b) {
  uint32_t x = ((const IdEntry *)a)->id, y = ((const IdEntry *)b)->id;
  return (x > y) - (x < y);
}

static void printSummary(uint32_t now) {
  qsort(ids, idCount, sizeof(IdEntry), cmpId);
  float secs = (now - lastSummary) / 1000.0f;
  if (secs <= 0) secs = 1;
  Serial.printf("\n--- %d ID, toplam %lu çerçeve, %lu kbps ---\n", idCount, (unsigned long)totalFrames, (unsigned long)bitrateKbps);
  Serial.println("ID        DLC   Hz     VERİ                      GÜRÜLTÜ MASKESİ");
  for (int i = 0; i < idCount; i++) {
    IdEntry &e = ids[i];
    Serial.print("  ");
    printId(e.id, e.extd);
    Serial.printf(e.extd ? "  %u  %6.1f   " : "       %u  %6.1f   ", e.dlc, (e.count - e.countAtLastSummary) / secs);
    for (int j = 0; j < 8; j++) {
      if (j < e.dlc) Serial.printf("%02X ", e.data[j]);
      else Serial.print("   ");
    }
    Serial.print("  ");
    for (int j = 0; j < e.dlc; j++) Serial.printf("%02X ", e.noise[j]);
    Serial.println();
    e.countAtLastSummary = e.count;
  }
  Serial.println();
  lastSummary = now;
}

static void printHelp() {
  Serial.println(F(
    "\nKomutlar:\n"
    "  c         Değişiklik modu (varsayılan): sadece değişen bitleri gösterir\n"
    "  r         Ham mod: her çerçeveyi candump biçiminde yazar (SavvyCAN'e aktarılabilir)\n"
    "  s         Özet: bütün ID'ler, frekansları ve son verileri\n"
    "  n         Gürültü öğren (5 sn): bu sürede kendiliğinden değişen bitler\n"
    "            (sayaçlar, sensör titremesi) bundan sonra gösterilmez.\n"
    "            Öğrenirken HİÇBİR şeye dokunmayın.\n"
    "  x         Gürültü maskelerini sıfırla\n"
    "  f 5DE     Sadece bu ID'yi göster     f   filtreyi kaldır\n"
    "  b 500     Hız seç: 125 / 250 / 500 / 1000 kbps\n"
    "  p         Duraklat / devam\n"
    "  t         Tabloyu temizle\n"
    "  h         Bu yardım\n"
    "\nYöntem: kontağı açın -> 'n' ile gürültüyü öğretin -> tek bir şey yapın\n"
    "(sol sinyal, far, el freni...) ve hangi bitin değiştiğine bakın.\n"));
}

static void handleCommand(char *line) {
  while (*line == ' ') line++;
  char cmd = line[0];
  char *arg = line + 1;
  while (*arg == ' ') arg++;

  switch (cmd) {
    case 'c': mode = MODE_CHANGES; Serial.println(F("> Değişiklik modu")); break;
    case 'r': mode = MODE_RAW;     Serial.println(F("> Ham mod")); break;
    case 's': printSummary(millis()); break;
    case 'n':
      learnUntil = millis() + 5000;
      if (learnUntil == 0) learnUntil = 1;
      Serial.println(F("> Gürültü öğreniliyor (5 sn), hiçbir şeye dokunmayın..."));
      break;
    case 'x':
      for (int i = 0; i < idCount; i++) memset(ids[i].noise, 0, 8);
      Serial.println(F("> Gürültü maskeleri sıfırlandı"));
      break;
    case 'f':
      if (*arg) {
        filterId = strtoul(arg, nullptr, 16);
        filterOn = true;
        Serial.printf("> Filtre: %lX\n", (unsigned long)filterId);
      } else {
        filterOn = false;
        Serial.println(F("> Filtre kaldırıldı"));
      }
      break;
    case 'b': {
      uint32_t kbps = strtoul(arg, nullptr, 10);
      canStop();
      resetTable();
      if (canStart(kbps)) Serial.printf("> %lu kbps dinleniyor\n", (unsigned long)bitrateKbps);
      else Serial.println(F("> CAN başlatılamadı!"));
      break;
    }
    case 'p': paused = !paused; Serial.println(paused ? F("> Duraklatıldı") : F("> Devam")); break;
    case 't': resetTable(); Serial.println(F("> Tablo temizlendi")); break;
    case 'h': case '?': printHelp(); break;
    default: break;
  }
}

static void readSerial() {
  static char buf[48];
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

void setup() {
  Serial.begin(921600);
  delay(300);
  Serial.println(F("\nKangoo CAN Sniffer (sadece dinler)"));
  if (canStart(bitrateKbps)) Serial.printf("%lu kbps dinleniyor. Yardım için 'h'.\n", (unsigned long)bitrateKbps);
  else Serial.println(F("CAN başlatılamadı! Pinleri kontrol edin."));
  lastSummary = millis();
}

void loop() {
  readSerial();

  twai_message_t m;
  while (twai_receive(&m, 0) == ESP_OK) {
    if (m.rtr) continue;
    totalFrames++;
    uint32_t now = millis();

    bool isNew = false;
    IdEntry *e = findOrAdd(m, &isNew);
    if (!e) continue;

    uint8_t oldData[8];
    uint8_t oldDlc = e->dlc;
    memcpy(oldData, e->data, 8);
    e->dlc = m.data_length_code > 8 ? 8 : m.data_length_code;
    memcpy(e->data, m.data, e->dlc);
    e->count++;

    if (learnUntil) {
      if (!isNew) {
        for (int i = 0; i < e->dlc && i < oldDlc; i++) e->noise[i] |= oldData[i] ^ e->data[i];
      }
      continue;
    }

    if (paused) continue;
    if (filterOn && e->id != filterId) continue;

    if (mode == MODE_RAW) {
      printRaw(m, micros());
    } else if (isNew) {
      printTime(now);
      Serial.print("YENİ ");
      printId(e->id, e->extd);
      Serial.printf(" [%u]", e->dlc);
      for (int i = 0; i < e->dlc; i++) Serial.printf(" %02X", e->data[i]);
      Serial.println();
    } else {
      bool changed = oldDlc != e->dlc;
      for (int i = 0; i < e->dlc && i < oldDlc && !changed; i++) {
        if ((oldData[i] ^ e->data[i]) & ~e->noise[i]) changed = true;
      }
      if (changed) printChange(*e, oldData, oldDlc, now);
    }
  }

  if (learnUntil && (int32_t)(millis() - learnUntil) >= 0) {
    learnUntil = 0;
    Serial.println(F("> Gürültü öğrenme bitti. Şimdi tek bir işlem yapın."));
  }
}
