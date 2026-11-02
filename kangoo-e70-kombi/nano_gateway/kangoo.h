#pragma once
// ============================================================================
//  Kangoo 2 (X61) CAN çözümleme
//
//  ÖNEMLİ: Aşağıdaki "ADAY" ID'ler aynı nesil Renault'larda (Megane 2,
//  Clio 3, Kangoo 2) forumlarda geçen değerlerdir. HİÇBİRİ sizin aracınızda
//  doğrulanmadı. Sniffer ile kontrol edin ve gerekirse düzeltin.
//  0x000 yazan sinyaller kapalıdır; sniffer ile bulup doldurun.
// ============================================================================

struct VehicleState {
  float rpm = 0;
  float speedKmh = 0;
  int   coolantC = 20;
  float fuelPct = 50;
  bool  turnLeft = false, turnRight = false;
  bool  lowBeam = false, highBeam = false, frontFog = false, rearFog = false;
  bool  handbrake = false;
  bool  warnBattery = false, warnOil = false, warnEngine = false;
  bool  warnAbs = false, warnAirbag = false, warnBrake = false;
  bool  ignitionOn = false;
};

// Tek bitlik sinyal: sniffer çıktısındaki "B2 m08" -> {ID, 2, 0x08}
struct BitSig {
  uint16_t id;
  uint8_t  byteIdx;
  uint8_t  mask;
  bool     inverted;   // bit 0 iken aktifse true
};

// ---- Çok baytlı değerler (USE_OBD_POLLING 0 iken kullanılır) ----
#define K_ID_RPM      0x186   // B0-B1 big endian / 8 = devir/dk      [ADAY]
#define K_ID_SPEED    0x354   // B0-B1 big endian / 100 = km/h         [ADAY]
#define K_ID_COOLANT  0x551   // B0 - 40 = °C                          [ADAY]

// ---- Tek bitlik sinyaller: sniffer ile bulun ----
static const BitSig SIG_TURN_LEFT  = {0x000, 0, 0x00, false};
static const BitSig SIG_TURN_RIGHT = {0x000, 0, 0x00, false};
static const BitSig SIG_LOW_BEAM   = {0x000, 0, 0x00, false};
static const BitSig SIG_HIGH_BEAM  = {0x000, 0, 0x00, false};
static const BitSig SIG_FRONT_FOG  = {0x000, 0, 0x00, false};
static const BitSig SIG_REAR_FOG   = {0x000, 0, 0x00, false};
static const BitSig SIG_HANDBRAKE  = {0x000, 0, 0x00, false};
static const BitSig SIG_W_BATTERY  = {0x000, 0, 0x00, false};
static const BitSig SIG_W_OIL      = {0x000, 0, 0x00, false};
static const BitSig SIG_W_ENGINE   = {0x000, 0, 0x00, false};
static const BitSig SIG_W_ABS      = {0x000, 0, 0x00, false};
static const BitSig SIG_W_AIRBAG   = {0x000, 0, 0x00, false};
static const BitSig SIG_W_BRAKE    = {0x000, 0, 0x00, false};

static const BitSig *const ALL_SIGS[] = {
  &SIG_TURN_LEFT, &SIG_TURN_RIGHT, &SIG_LOW_BEAM, &SIG_HIGH_BEAM, &SIG_FRONT_FOG,
  &SIG_REAR_FOG, &SIG_HANDBRAKE, &SIG_W_BATTERY, &SIG_W_OIL, &SIG_W_ENGINE,
  &SIG_W_ABS, &SIG_W_AIRBAG, &SIG_W_BRAKE,
};

static inline void applyBit(const BitSig &s, uint16_t id, const can_frame &f, bool &out) {
  if (s.id == 0 || id != s.id || s.byteIdx >= f.can_dlc) return;
  bool v = (f.data[s.byteIdx] & s.mask) != 0;
  out = s.inverted ? !v : v;
}

static void decodeKangooFrame(const can_frame &f, VehicleState &st) {
  if (f.can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG)) return;
  uint16_t id = f.can_id & CAN_SFF_MASK;
  const uint8_t *d = f.data;

#if !USE_OBD_POLLING
  if (id == K_ID_RPM && f.can_dlc >= 2)
    st.rpm = ((uint16_t)(d[0] << 8) | d[1]) / 8.0f;
  if (id == K_ID_SPEED && f.can_dlc >= 2)
    st.speedKmh = ((uint16_t)(d[0] << 8) | d[1]) / 100.0f;
  if (id == K_ID_COOLANT && f.can_dlc >= 1)
    st.coolantC = (int)d[0] - 40;
#else
  // OBD yanıtı (tek çerçeve): [uzunluk] 41 [PID] A B ...
  if (id == OBD_RESP_ID && f.can_dlc >= 4 && d[1] == 0x41) {
    switch (d[2]) {
      case 0x0C: if (d[0] >= 4) st.rpm = ((uint16_t)(d[3] << 8) | d[4]) / 4.0f; break;
      case 0x0D: st.speedKmh = d[3]; break;
      case 0x05: st.coolantC = (int)d[3] - 40; break;
    }
  }
#endif

  applyBit(SIG_TURN_LEFT,  id, f, st.turnLeft);
  applyBit(SIG_TURN_RIGHT, id, f, st.turnRight);
  applyBit(SIG_LOW_BEAM,   id, f, st.lowBeam);
  applyBit(SIG_HIGH_BEAM,  id, f, st.highBeam);
  applyBit(SIG_FRONT_FOG,  id, f, st.frontFog);
  applyBit(SIG_REAR_FOG,   id, f, st.rearFog);
  applyBit(SIG_HANDBRAKE,  id, f, st.handbrake);
  applyBit(SIG_W_BATTERY,  id, f, st.warnBattery);
  applyBit(SIG_W_OIL,      id, f, st.warnOil);
  applyBit(SIG_W_ENGINE,   id, f, st.warnEngine);
  applyBit(SIG_W_ABS,      id, f, st.warnAbs);
  applyBit(SIG_W_AIRBAG,   id, f, st.warnAirbag);
  applyBit(SIG_W_BRAKE,    id, f, st.warnBrake);
}

// MCP2515 donanım filtresi için dinlenecek ID'leri toplar (en fazla 6).
// 6'dan fazlaysa ya da hiç yoksa 0 döner: her şey kabul edilir.
static uint8_t collectFilterIds(uint16_t *out) {
  uint8_t n = 0;
  auto add = [&](uint16_t id) {
    if (id == 0) return;
    for (uint8_t i = 0; i < n; i++) if (out[i] == id) return;
    if (n < 6) out[n] = id;
    n++;
  };
#if USE_OBD_POLLING
  add(OBD_RESP_ID);
#else
  add(K_ID_RPM);
  add(K_ID_SPEED);
  add(K_ID_COOLANT);
#endif
  for (const BitSig *s : ALL_SIGS) add(s->id);
  return n <= 6 ? n : 0;
}

// ---- OBD sorgusu: devir iki kat sık sorulur, sıcaklık yavaş değişir ----
static const uint8_t OBD_PIDS[] = {0x0C, 0x0D, 0x0C, 0x0D, 0x0C, 0x0D, 0x05};

static void fillObdRequest(can_frame &q) {
  static uint8_t idx = 0;
  memset(&q, 0, sizeof(q));
  q.can_id = OBD_REQ_ID;
  q.can_dlc = 8;
  q.data[0] = 0x02;
  q.data[1] = 0x01;
  q.data[2] = OBD_PIDS[idx];
  idx = (idx + 1) % sizeof(OBD_PIDS);
}
