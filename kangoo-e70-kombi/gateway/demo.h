#pragma once
// ============================================================================
//  Test modu: "trafikteymiş gibi" sürüş taklidi ("demo 1" ile açılır)
//
//  Önce ibre testi yapılır (devir ve hız sona kadar gidip döner). Sonra
//  rastgele olaylar sırayla gelir: kırmızı ışık, şehir içi, kalk-dur, dönüş
//  (sinyal verip yavaşlama), çevre yolu, ara sıra sert gaz. Sürücü hedef hıza
//  göre gaz/fren yapar, vites büyütür/küçültür, motor suyu ısınır, yakıt azalır.
// ============================================================================

#define DEMO_IDLE_RPM   800
#define DEMO_MAX_RPM    7000    // ibre testi için
#define DEMO_MAX_SPEED  260     // ibre testi için

// Her viteste 1 km/h başına devir (Kangoo 1.5 dCi'ye yakın oranlar)
static const float DEMO_RPM_PER_KMH[] = {0, 115, 62, 40, 30, 24};
static const uint8_t DEMO_TOP_GEAR = 5;

enum DemoEvent : uint8_t {
  EV_SWEEP,       // ibre testi
  EV_RED_LIGHT,   // kırmızı ışık: dur, rölantide bekle
  EV_CITY,        // şehir içi 30-60
  EV_STOP_GO,     // sıkışık trafik 5-20
  EV_TURN,        // sinyal ver, yavaşla, dön, hızlan
  EV_RING_ROAD,   // çevre yolu 70-100
  EV_SPORT,       // sert gaz: yüksek devirde vites
};

struct DemoState {
  bool     on = false;
  DemoEvent ev = EV_SWEEP;
  uint32_t evStart = 0, evLen = 0, last = 0;
  uint8_t  gear = 1;
  float    target = 0;        // hedef hız
  float    accel = 10;        // km/h/s, birinci viteste
  float    brake = 12;        // km/h/s
  uint16_t shiftUp = 2500;    // bu devirde vites büyütür
  bool     turnLeftSide = true;
  float    coolant = 20;
};

static DemoState demo;

static void demoNextEvent(VehicleState &st, uint32_t now) {
  demo.evStart = now;
  demo.accel = random(7, 13);
  demo.brake = random(8, 16);
  demo.shiftUp = random(2000, 3000);
  st.turnLeft = st.turnRight = false;
  st.handbrake = false;

  long r = random(100);
  if (r < 22)      { demo.ev = EV_RED_LIGHT; demo.target = 0;                 demo.evLen = random(9000, 16000); }
  else if (r < 50) { demo.ev = EV_CITY;      demo.target = random(30, 61);    demo.evLen = random(6000, 12000); }
  else if (r < 65) { demo.ev = EV_STOP_GO;   demo.target = random(5, 21);     demo.evLen = random(3000, 6000); }
  else if (r < 82) { demo.ev = EV_TURN;      demo.target = random(12, 20);    demo.evLen = random(7000, 10000);
                     demo.turnLeftSide = random(2); }
  else if (r < 93) { demo.ev = EV_RING_ROAD; demo.target = random(70, 101);   demo.evLen = random(10000, 16000); }
  else             { demo.ev = EV_SPORT;     demo.target = random(90, 121);   demo.evLen = random(8000, 11000);
                     demo.accel = 16; demo.shiftUp = 4300; }
}

static void demoStart(VehicleState &st, uint32_t now) {
  demo = DemoState();
  demo.on = true;
  demo.ev = EV_SWEEP;
  demo.evStart = demo.last = now;
  demo.evLen = 2400;
  st = VehicleState();
  st.ignitionOn = true;
  st.fuelPct = 75;
  st.parkLights = st.lowBeam = true;
  randomSeed(now ^ 0x5A5A);
}

static void demoUpdate(VehicleState &st, uint32_t now) {
  if (!demo.on) return;
  uint32_t dtMs = now - demo.last;
  if (dtMs < 40) return;
  demo.last = now;
  float dt = dtMs / 1000.0f;
  uint32_t t = now - demo.evStart;

  // Motor suyu yavaşça 90°C'ye ısınır, yakıt azalır (bitince yeniden doldurulur)
  if (demo.coolant < 90) demo.coolant += 1.5f * dt;
  st.coolantC = (int)demo.coolant;
  st.fuelPct -= 0.15f * dt;
  if (st.fuelPct < 8) st.fuelPct = 75;

  if (demo.ev == EV_SWEEP) {
    // 0 -> tam -> 0, BMW'nin açılış animasyonu gibi
    float p = t < 1200 ? t / 1200.0f : (t < 2400 ? (2400 - t) / 1200.0f : 0);
    st.rpm = p * DEMO_MAX_RPM;
    st.speedKmh = p * DEMO_MAX_SPEED;
    if (t >= demo.evLen) {
      st.rpm = DEMO_IDLE_RPM;
      st.speedKmh = 0;
      demoNextEvent(st, now);
    }
    return;
  }

  // Dönüş: önce sinyal + yavaşlama, sonra dönüp şehir içi hıza çıkma
  if (demo.ev == EV_TURN) {
    bool signalling = t < 5500;
    (demo.turnLeftSide ? st.turnLeft : st.turnRight) = signalling;
    if (t > 4500) demo.target = 40;
  }
  // Kırmızı ışık: durduktan sonra el freni, yeşilden hemen önce indirilir
  if (demo.ev == EV_RED_LIGHT) {
    st.handbrake = st.speedKmh < 1 && t > 3000 && t + 1500 < demo.evLen;
  }
  // Sıkışık trafik: hedef sürekli değişir
  if (demo.ev == EV_STOP_GO && random(100) < 3) demo.target = random(0, 21);

  // ---- Sürücü: hedef hıza göre gaz / fren ----
  float diff = demo.target - st.speedKmh;
  if (diff > 1.5f) {
    st.speedKmh += demo.accel * dt * (1.6f / (demo.gear + 0.6f));
  } else if (diff < -1.5f) {
    st.speedKmh -= demo.brake * dt;
  } else if (demo.target > 5) {
    st.speedKmh += (random(-10, 11) / 10.0f) * dt;   // seyirde hafif dalgalanma
  }
  if (st.speedKmh < 0 || (demo.target == 0 && st.speedKmh < 2)) st.speedKmh = 0;

  // ---- Vites ----
  float rpm = st.speedKmh * DEMO_RPM_PER_KMH[demo.gear];
  if (diff > 1.5f && rpm > demo.shiftUp && demo.gear < DEMO_TOP_GEAR) {
    demo.gear++;                                  // vites büyüt: devir düşer
    rpm = st.speedKmh * DEMO_RPM_PER_KMH[demo.gear];
  } else if (rpm < 1250 && demo.gear > 1) {
    demo.gear--;                                  // vites küçült: devir zıplar
    rpm = st.speedKmh * DEMO_RPM_PER_KMH[demo.gear];
  }
  if (demo.gear == 1 && rpm < 1100) {
    // birinci viteste kalkış (debriyaj kaydırma) ya da duruş (rölanti)
    rpm = (diff > 1.5f) ? 1100 + random(0, 300) : DEMO_IDLE_RPM + random(-25, 26);
  }
  st.rpm = rpm;

  if (t >= demo.evLen) demoNextEvent(st, now);
}
