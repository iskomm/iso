#pragma once
// ============================================================================
//  Donanım ve genel ayarlar — Arduino Nano / Uno (ATmega328P)
// ============================================================================

// İki MCP2515 modülü aynı SPI hattını paylaşır, sadece CS pinleri ayrı:
//  D13=SCK  D12=SO  D11=SI  (iki modülde ortak)
#define BMW_CS_PIN        10    // BMW göstergesi tarafı (100 kbps)
#define KANGOO_CS_PIN     9     // Kangoo tarafı (500 kbps)

// Modüllerin üzerindeki kristal: 8.000 -> MCP_8MHZ, 16.000 -> MCP_16MHZ
#define BMW_MCP_CLOCK     MCP_8MHZ
#define KANGOO_MCP_CLOCK  MCP_8MHZ

// ---- BMW PT-CAN (opsiyonel, ayrı bir MCP2515) ----
// E70 göstergesi devri PT-CAN'den (500 kbps) okuyorsa: göstergenin PT-CAN
// pinlerine ayrı bir MCP2515 bağlayıp 1 yapın. Bütün BMW mesajları oraya da
// kopyalanır. Masada Kangoo modülü yokken D9'daki modülü de kullanabilirsiniz
// (KANGOO_ENABLED 0 ve BMW_PTCAN_CS 9).
#define BMW_PTCAN_ENABLED 0
#define BMW_PTCAN_CS      8
#define BMW_PTCAN_CLOCK   MCP_8MHZ

// Kangoo tarafındaki ikinci MCP2515 henüz bağlı değilse (masa testi) 0 yapın.
// 1 iken modül bulunamazsa program yine çalışır, sadece uyarı verir.
#define KANGOO_ENABLED    1

// ---- Devir / hız / motor suyu sıcaklığı kaynağı ----
// 1: Motor beynine standart OBD sorgusu gönderilir (PID 0C, 0D, 05).
//    Tersine mühendislik gerektirmez, hemen çalışır. Araç hattına sadece
//    arıza tespit cihazının gönderdiği türden istek mesajları gider.
//    Güvenlik için önce dinleme modunda açılır; hattan düzgün mesaj
//    alındığı görülmeden asla gönderim yapılmaz.
// 0: Hiç gönderim yapılmaz (tamamen dinleme). Bu değerler kangoo.h'daki
//    yayın (broadcast) ID'lerinden okunur, onları sniffer ile bulmanız gerekir.
#define USE_OBD_POLLING   1
#define OBD_REQ_ID        0x7E0   // motor beyni fiziksel adresi
#define OBD_RESP_ID       0x7E8
#define OBD_PERIOD_MS     40      // istekler arası süre

// ---- Yakıt seviyesi ----
// Kangoo'da yakıt şamandırası büyük ihtimalle doğrudan orijinal göstergeye
// bağlı ve CAN'de olmayabilir. 1 yaparsanız şamandıra hattının gerilimi
// A0'dan okunur (yüksek dirençli bölücü ile, bkz. README).
#define USE_FUEL_ADC      0
#define FUEL_ADC_PIN      A0
#define FUEL_ADC_EMPTY    800     // depo boşken okunan ham değer, 0-1023 (ölçün)
#define FUEL_ADC_FULL     150     // depo doluyken okunan ham değer (ölçün)

// Kangoo hattı bu kadar süre sessiz kalırsa kontak kapalı sayılır,
// BMW göstergesine gönderim durur ve gösterge uyku moduna geçer.
#define BUS_TIMEOUT_MS    1500

// Dinleme modundan normal moda geçmeden önce alınması gereken düzgün çerçeve sayısı
#define FRAMES_BEFORE_TX  200
