// Kangoo CAN Sniffer — Arduino Nano (ya da Uno) + MCP2515
//
// Aracın CAN hattını SADECE DİNLER (MCP2515 listen-only modu): hiçbir mesaj
// göndermez, ACK bile vermez. Araca zarar veremez.
//
// Bağlantı:  D13 -> SCK   D12 -> SO   D11 -> SI   D10 -> CS   5V -> VCC   GND -> GND
//            MCP2515 CANH -> OBD pin 6,  CANL -> OBD pin 14,  GND -> OBD pin 4/5
//            MCP2515 modülündeki 120 Ω jumper'ı ÇIKARIN (araç hattı zaten sonlandırılmış).
//
// Gerekli kütüphane: autowp-mcp2515
// Seri monitör: 115200 baud, satır sonu "Newline". Komutlar için "h" yazın.
//
// Not: Nano'nun belleği ve MCP2515'in 2 alım tamponu sınırlı. Yoğun hatta bazı
// çerçeveler kaçabilir; değişiklik modunda bu sorun olmaz.

#include <SPI.h>
#include <mcp2515.h>

#define CS_PIN      10
#define MCP_CLOCK   MCP_8MHZ    // kristalde 16.000 yazıyorsa MCP_16MHZ

enum Mode { MODE_CHANGES, MODE_RAW };

struct IdEntry {
  uint16_t id;
  uint8_t  dlc;
  uint8_t  data[8];
  uint8_t  noise[8];     // kendi kendine değişen bitler (sayaçlar vb.)
  uint16_t count;
};

static const int MAX_IDS = 40;
static IdEntry ids[MAX_IDS];
static int idCount = 0;

static MCP2515 mcp(CS_PIN);
static Mode mode = MODE_CHANGES;
static uint16_t bitrateKbps = 500;
static bool paused = false;
static bool filterOn = false;
static uint16_t filterId = 0;
static uint32_t learnUntil = 0;     // 0 değilse gürültü öğrenme sürüyor
static uint32_t lastSummary = 0;
static uint32_t totalFrames = 0;

static void printHex2(uint8_t v) {
  if (v < 0x10) Serial.print('0');
  Serial.print(v, HEX);
}

static void printId(uint16_t id) {
  if (id < 0x100) Serial.print('0');
  if (id < 0x10) Serial.print('0');
  Serial.print(id, HEX);
}

static void printTime(uint32_t ms) {
  Serial.print(ms / 1000);
  Serial.print('.');
  uint16_t r = ms % 1000;
  if (r < 100) Serial.print('0');
  if (r < 10) Serial.print('0');
  Serial.print(r);
  Serial.print(' ');
}

static bool canStart(uint16_t kbps) {
  CAN_SPEED s;
  switch (kbps) {
    case 125:  s = CAN_125KBPS;  break;
    case 250:  s = CAN_250KBPS;  break;
    case 1000: s = CAN_1000KBPS; break;
    default:   s = CAN_500KBPS;  kbps = 500; break;
  }
  mcp.reset();
  if (mcp.setBitrate(s, MCP_CLOCK) != MCP2515::ERROR_OK) return false;
  if (mcp.setListenOnlyMode() != MCP2515::ERROR_OK) return false;
  bitrateKbps = kbps;
  return true;
}

static IdEntry *findOrAdd(uint16_t id, bool *isNew) {
  for (int i = 0; i < idCount; i++) {
    if (ids[i].id == id) {
      *isNew = false;
      return &ids[i];
    }
  }
  if (idCount >= MAX_IDS) return nullptr;
  IdEntry *e = &ids[idCount++];
  memset(e, 0, sizeof(*e));
  e->id = id;
  *isNew = true;
  return e;
}

// candump log biçimi: SavvyCAN ve can-utils bunu içe aktarabilir.
static void printRaw(const can_frame &f, uint32_t us) {
  Serial.print('(');
  Serial.print(us / 1000000);
  Serial.print('.');
  char buf[7];
  snprintf(buf, sizeof(buf), "%06lu", (unsigned long)(us % 1000000));
  Serial.print(buf);
  Serial.print(F(") can0 "));
  printId(f.can_id & CAN_SFF_MASK);
  Serial.print('#');
  for (int i = 0; i < f.can_dlc; i++) printHex2(f.data[i]);
  Serial.println();
}

// Değişen baytları [köşeli parantez] içinde gösterir, sonra hangi bitin nasıl
// değiştiğini yazar. Örn: "B2 m08 0>1" = 3. bayt, maske 0x08, 0'dan 1'e.
// Bu bilgiyi doğrudan nano_gateway/kangoo.h içindeki BitSig tanımına yazabilirsiniz.
static void printChange(const IdEntry &e, const uint8_t *oldData, uint8_t oldDlc, uint32_t ms) {
  printTime(ms);
  printId(e.id);
  Serial.print(F(" ["));
  Serial.print(e.dlc);
  Serial.print(F("] "));
  for (int i = 0; i < e.dlc; i++) {
    uint8_t diff = (i < oldDlc) ? ((oldData[i] ^ e.data[i]) & ~e.noise[i]) : 0xFF;
    Serial.print(diff ? '[' : ' ');
    printHex2(e.data[i]);
    Serial.print(diff ? ']' : ' ');
  }
  Serial.print(' ');
  for (int i = 0; i < e.dlc && i < oldDlc; i++) {
    uint8_t diff = (oldData[i] ^ e.data[i]) & ~e.noise[i];
    for (int b = 7; b >= 0; b--) {
      uint8_t mask = 1 << b;
      if (diff & mask) {
        Serial.print(F(" B"));
        Serial.print(i);
        Serial.print(F(" m"));
        printHex2(mask);
        Serial.print(' ');
        Serial.print((oldData[i] & mask) ? 1 : 0);
        Serial.print('>');
        Serial.print((e.data[i] & mask) ? 1 : 0);
      }
    }
  }
  Serial.println();
}

static int cmpId(const void *a, const void *b) {
  uint16_t x = ((const IdEntry *)a)->id, y = ((const IdEntry *)b)->id;
  return (x > y) - (x < y);
}

static void printSummary(uint32_t now) {
  qsort(ids, idCount, sizeof(IdEntry), cmpId);
  float secs = (now - lastSummary) / 1000.0f;
  if (secs <= 0) secs = 1;
  Serial.println();
  Serial.print(F("--- "));
  Serial.print(idCount);
  Serial.print(F(" ID, toplam "));
  Serial.print(totalFrames);
  Serial.print(F(" çerçeve, "));
  Serial.print(bitrateKbps);
  Serial.println(F(" kbps ---"));
  Serial.println(F("ID    DLC  Hz      VERİ                     GÜRÜLTÜ MASKESİ"));
  for (int i = 0; i < idCount; i++) {
    IdEntry &e = ids[i];
    printId(e.id);
    Serial.print(F("   "));
    Serial.print(e.dlc);
    Serial.print(F("  "));
    Serial.print(e.count / secs, 1);
    Serial.print(F("\t"));
    for (int j = 0; j < 8; j++) {
      if (j < e.dlc) { printHex2(e.data[j]); Serial.print(' '); }
      else Serial.print(F("   "));
    }
    Serial.print(F(" "));
    for (int j = 0; j < e.dlc; j++) { printHex2(e.noise[j]); Serial.print(' '); }
    Serial.println();
    e.count = 0;
  }
  Serial.println();
  lastSummary = now;
}

static void printHelp() {
  Serial.println(F(
    "\nKomutlar:\n"
    "  c         Değişiklik modu (varsayılan): sadece değişen bitleri gösterir\n"
    "  r         Ham mod: her çerçeveyi candump biçiminde yazar\n"
    "  s         Özet: bütün ID'ler, frekansları ve son verileri\n"
    "  n         Gürültü öğren (5 sn): bu sürede kendiliğinden değişen bitler\n"
    "            bundan sonra gösterilmez. Öğrenirken HİÇBİR şeye dokunmayın.\n"
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
        Serial.print(F("> Filtre: "));
        printId(filterId);
        Serial.println();
      } else {
        filterOn = false;
        Serial.println(F("> Filtre kaldırıldı"));
      }
      break;
    case 'b': {
      uint16_t kbps = strtoul(arg, nullptr, 10);
      idCount = 0;
      totalFrames = 0;
      if (canStart(kbps)) {
        Serial.print(F("> "));
        Serial.print(bitrateKbps);
        Serial.println(F(" kbps dinleniyor"));
      } else {
        Serial.println(F("> MCP2515 başlatılamadı!"));
      }
      break;
    }
    case 'p': paused = !paused; Serial.println(paused ? F("> Duraklatıldı") : F("> Devam")); break;
    case 't': idCount = 0; totalFrames = 0; Serial.println(F("> Tablo temizlendi")); break;
    case 'h': case '?': printHelp(); break;
    default: break;
  }
}

static void readSerial() {
  static char buf[24];
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
  Serial.begin(115200);
  Serial.println(F("\nKangoo CAN Sniffer - Nano (sadece dinler)"));
  if (canStart(bitrateKbps)) {
    Serial.print(bitrateKbps);
    Serial.println(F(" kbps dinleniyor. Yardım için 'h'."));
  } else {
    Serial.println(F("MCP2515 başlatılamadı! Kabloları ve kristal ayarını kontrol edin."));
  }
  lastSummary = millis();
}

void loop() {
  readSerial();

  can_frame f;
  while (mcp.readMessage(&f) == MCP2515::ERROR_OK) {
    if (f.can_id & (CAN_RTR_FLAG | CAN_EFF_FLAG)) continue;
    totalFrames++;
    uint32_t now = millis();
    uint16_t id = f.can_id & CAN_SFF_MASK;

    bool isNew = false;
    IdEntry *e = findOrAdd(id, &isNew);
    if (!e) continue;

    uint8_t oldData[8];
    uint8_t oldDlc = e->dlc;
    memcpy(oldData, e->data, 8);
    e->dlc = f.can_dlc > 8 ? 8 : f.can_dlc;
    memcpy(e->data, f.data, e->dlc);
    e->count++;

    if (learnUntil) {
      if (!isNew) {
        for (int i = 0; i < e->dlc && i < oldDlc; i++) e->noise[i] |= oldData[i] ^ e->data[i];
      }
      continue;
    }

    if (paused) continue;
    if (filterOn && id != filterId) continue;

    if (mode == MODE_RAW) {
      printRaw(f, micros());
    } else if (isNew) {
      printTime(now);
      Serial.print(F("YENİ "));
      printId(id);
      Serial.print(F(" ["));
      Serial.print(e->dlc);
      Serial.print(']');
      for (int i = 0; i < e->dlc; i++) { Serial.print(' '); printHex2(e->data[i]); }
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
