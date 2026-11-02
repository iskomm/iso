#pragma once
// ============================================================================
//  BMW E70 KOMBI — K-CAN (100 kbps) mesajları
//
//  Bu mesaj biçimleri E90 gösterge projelerinden bilinen değerlerdir. E70
//  aynı nesil (E serisi) olduğu için büyük oranda aynı olması beklenir ama
//  her birini MASADA test edin. Seri monitörden "raw", "rep", "on"/"off"
//  komutlarıyla değiştirip deneyebilirsiniz; doğru değeri bulunca buraya yazın.
// ============================================================================

struct Slot {
  uint16_t id;
  uint16_t periodMs;
  uint8_t  dlc;
  uint8_t  data[8];
  bool     enabled;
  uint32_t last;
};

enum {
  S_TERMINAL,   // 0x130 kontak durumu (normalde CAS gönderir)
  S_RPM,        // 0x0AA devir
  S_SPEED,      // 0x1A6 hız / mesafe sayacı
  S_TEMP,       // 0x1D0 motor suyu sıcaklığı
  S_FUEL,       // 0x349 yakıt seviyesi
  S_LIGHTS,     // 0x21A farlar
  S_TURN,       // 0x1F6 sinyaller
  S_HANDBRAKE,  // 0x34F el freni
  S_ALIVE,      // 0x0C0 canlılık sayacı
  S_DIMMER,     // 0x202 gösterge aydınlatması
  S_STD_COUNT,
  S_CUSTOM_FIRST = S_STD_COUNT,
  S_TOTAL = S_STD_COUNT + 4   // "rep" komutu için 4 serbest yuva (Nano belleği küçük)
};

static Slot slots[S_TOTAL] = {
  {0x130, 100, 5, {0x45, 0x42, 0x69, 0x8F, 0xE2}, true, 0},
  {0x0AA, 100, 8, {0x5F, 0x59, 0xFF, 0x00, 0x00, 0x00, 0x80, 0x99}, true, 0},
  {0x1A6, 100, 8, {0}, true, 0},
  {0x1D0, 200, 8, {0x00, 0xFF, 0x63, 0xCD, 0x5D, 0x37, 0xCD, 0xA8}, true, 0},
  {0x349, 200, 5, {0}, true, 0},
  {0x21A, 100, 3, {0x00, 0x00, 0xF7}, true, 0},
  {0x1F6, 100, 2, {0x80, 0xF0}, true, 0},
  {0x34F, 200, 2, {0xFD, 0xFF}, true, 0},
  {0x0C0, 200, 2, {0xF0, 0xFF}, true, 0},
  {0x202, 500, 2, {0xFD, 0xFF}, true, 0},
};

// ---- Kalibrasyon (seri monitörden "cal" ve "fcal" ile değiştirilebilir) ----
// Hız: masada "spd 100" verip ibre 100'ü gösterene kadar "cal" ile ayarlayın.
// Kilometre sayacı da bu sayaçtan saydığı için GPS ile ayrıca doğrulayın.
static float speedScale = 1.0f;
static uint16_t fuelRawEmpty = 0x0000;
static uint16_t fuelRawFull  = 0x1F40;

// ---- 0x21A far bitleri [doğrulanmalı] ----
#define LIGHT_LOW_BEAM   0x04
#define LIGHT_HIGH_BEAM  0x02
#define LIGHT_FRONT_FOG  0x20
#define LIGHT_REAR_FOG   0x40

// ---- Uyarı lambaları: Check Control mesajı (0x592) ----
// E serisinde birçok uyarı lambası Check Control numarasıyla yakılır.
// Numaraları masada "cc <numara> 1" ile deneyerek bulun ve buraya yazın.
// 0 = kapalı.
static uint16_t ccBattery = 0;
static uint16_t ccOil     = 0;
static uint16_t ccEngine  = 0;
static uint16_t ccAbs     = 0;
static uint16_t ccAirbag  = 0;
static uint16_t ccBrake   = 0;

static float    speedDist = 0;     // 0x1A6 mesafe sayacı (kesirli birikim)
static uint16_t speedTick = 0;     // 0x1A6 zaman sayacı
static uint8_t  aliveCnt  = 0;

static void buildSlot(int i, const VehicleState &st, uint32_t dtMs) {
  uint8_t *d = slots[i].data;
  switch (i) {
    case S_RPM: {
      uint16_t v = (uint16_t)(st.rpm * 4);
      d[4] = v & 0xFF;
      d[5] = v >> 8;
      break;
    }
    case S_SPEED: {
      speedDist += st.speedKmh * speedScale * dtMs / 100.0f;
      if (speedDist >= 65536.0f) speedDist -= 65536.0f;   // float hassasiyeti kaybolmasın
      speedTick += dtMs * 2;
      uint16_t c = (uint16_t)((uint32_t)speedDist & 0xFFFF);
      d[0] = d[2] = d[4] = c & 0xFF;
      d[1] = d[3] = d[5] = c >> 8;
      d[6] = speedTick & 0xFF;
      d[7] = 0xF0 | ((speedTick >> 8) & 0x0F);
      break;
    }
    case S_TEMP:
      d[0] = (uint8_t)constrain(st.coolantC + 48, 0, 255);
      break;
    case S_FUEL: {
      float p = constrain(st.fuelPct, 0.0f, 100.0f) / 100.0f;
      uint16_t v = (uint16_t)(fuelRawEmpty + p * (fuelRawFull - fuelRawEmpty));
      d[0] = d[2] = v & 0xFF;
      d[1] = d[3] = v >> 8;
      d[4] = 0x00;
      break;
    }
    case S_LIGHTS:
      d[0] = (st.lowBeam  ? LIGHT_LOW_BEAM  : 0) | (st.highBeam ? LIGHT_HIGH_BEAM : 0) |
             (st.frontFog ? LIGHT_FRONT_FOG : 0) | (st.rearFog  ? LIGHT_REAR_FOG  : 0);
      break;
    case S_TURN:
      if (st.turnLeft && st.turnRight) { d[0] = 0xB1; d[1] = 0xF2; }
      else if (st.turnLeft)            { d[0] = 0x91; d[1] = 0xF2; }
      else if (st.turnRight)           { d[0] = 0xA1; d[1] = 0xF2; }
      else                             { d[0] = 0x80; d[1] = 0xF0; }
      break;
    case S_HANDBRAKE:
      d[0] = st.handbrake ? 0xFE : 0xFD;
      break;
    case S_ALIVE:
      d[0] = 0xF0 | aliveCnt;
      aliveCnt = (aliveCnt + 1) % 15;
      break;
  }
}

// Check Control: [40] [numara L] [numara H] [31=yak / 30=söndür] FF FF FF FF
static void fillCheckControl(struct can_frame &f, uint16_t num, bool on) {
  f.can_id = 0x592;
  f.can_dlc = 8;
  f.data[0] = 0x40;
  f.data[1] = num & 0xFF;
  f.data[2] = num >> 8;
  f.data[3] = on ? 0x31 : 0x30;
  f.data[4] = f.data[5] = f.data[6] = f.data[7] = 0xFF;
}
