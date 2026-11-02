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
  bool  parkLights = false;
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
static const BitSig SIG_PARK       = {0x000, 0, 0x00, false};
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

static inline void applyBit(const BitSig &s, const twai_message_t &m, bool &out) {
  if (s.id == 0 || m.identifier != s.id || s.byteIdx >= m.data_length_code) return;
  bool v = (m.data[s.byteIdx] & s.mask) != 0;
  out = s.inverted ? !v : v;
}

static void decodeKangooFrame(const twai_message_t &m, VehicleState &st) {
  if (m.extd || m.rtr) return;
  const uint8_t *d = m.data;

#if !USE_OBD_POLLING
  if (m.identifier == K_ID_RPM && m.data_length_code >= 2)
    st.rpm = ((d[0] << 8) | d[1]) / 8.0f;
  if (m.identifier == K_ID_SPEED && m.data_length_code >= 2)
    st.speedKmh = ((d[0] << 8) | d[1]) / 100.0f;
  if (m.identifier == K_ID_COOLANT && m.data_length_code >= 1)
    st.coolantC = (int)d[0] - 40;
#else
  // OBD yanıtı (tek çerçeve): [uzunluk] 41 [PID] A B ...
  if (m.identifier == OBD_RESP_ID && m.data_length_code >= 4 && d[1] == 0x41) {
    switch (d[2]) {
      case 0x0C: if (d[0] >= 4) st.rpm = ((d[3] << 8) | d[4]) / 4.0f; break;
      case 0x0D: st.speedKmh = d[3]; break;
      case 0x05: st.coolantC = (int)d[3] - 40; break;
    }
  }
#endif

  applyBit(SIG_TURN_LEFT,  m, st.turnLeft);
  applyBit(SIG_TURN_RIGHT, m, st.turnRight);
  applyBit(SIG_PARK,       m, st.parkLights);
  applyBit(SIG_LOW_BEAM,   m, st.lowBeam);
  applyBit(SIG_HIGH_BEAM,  m, st.highBeam);
  applyBit(SIG_FRONT_FOG,  m, st.frontFog);
  applyBit(SIG_REAR_FOG,   m, st.rearFog);
  applyBit(SIG_HANDBRAKE,  m, st.handbrake);
  applyBit(SIG_W_BATTERY,  m, st.warnBattery);
  applyBit(SIG_W_OIL,      m, st.warnOil);
  applyBit(SIG_W_ENGINE,   m, st.warnEngine);
  applyBit(SIG_W_ABS,      m, st.warnAbs);
  applyBit(SIG_W_AIRBAG,   m, st.warnAirbag);
  applyBit(SIG_W_BRAKE,    m, st.warnBrake);
}

// ---- OBD sorgusu: devir iki kat sık sorulur, sıcaklık yavaş değişir ----
static const uint8_t OBD_PIDS[] = {0x0C, 0x0D, 0x0C, 0x0D, 0x0C, 0x0D, 0x05};

static bool obdSendNext() {
  static uint8_t idx = 0;
  twai_message_t q = {};
  q.identifier = OBD_REQ_ID;
  q.data_length_code = 8;
  q.data[0] = 0x02;
  q.data[1] = 0x01;
  q.data[2] = OBD_PIDS[idx];
  idx = (idx + 1) % sizeof(OBD_PIDS);
  return twai_transmit(&q, 0) == ESP_OK;
}
