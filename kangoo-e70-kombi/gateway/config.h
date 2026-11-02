#pragma once
// ============================================================================
//  Donanım ve genel ayarlar
// ============================================================================

// ---- Kangoo tarafı: ESP32 dahili TWAI + SN65HVD230 (3.3V) ----
#define KANGOO_CAN_TX   GPIO_NUM_25
#define KANGOO_CAN_RX   GPIO_NUM_26

// ---- BMW tarafı: MCP2515 modülü (SPI) ----
//  SCK=18  MISO(SO)=19  MOSI(SI)=23  CS=4
#define BMW_CS_PIN      4
// Modül üzerindeki kristalin üstünde yazan değer: 8.000 -> MCP_8MHZ, 16.000 -> MCP_16MHZ
#define BMW_MCP_CLOCK   MCP_8MHZ
// Seviye dönüştürücü (BSS138) kullanıyorsanız 1 MHz yeterli ve güvenli.
#define BMW_SPI_HZ      1000000

// ---- Devir / hız / motor suyu sıcaklığı kaynağı ----
// 1: Motor beynine standart OBD sorgusu gönderilir (PID 0C, 0D, 05).
//    Tersine mühendislik gerektirmez, hemen çalışır. ESP32 araç hattına
//    sadece arıza tespit cihazının gönderdiği türden istek mesajları yollar.
//    Güvenlik için önce dinleme modunda açılır; hattan düzgün mesaj
//    alındığı görülmeden asla gönderim yapılmaz.
// 0: Hiç gönderim yapılmaz (tamamen dinleme). Bu değerler kangoo.h'daki
//    yayın (broadcast) ID'lerinden okunur, onları sniffer ile bulmanız gerekir.
#define USE_OBD_POLLING 1
#define OBD_REQ_ID      0x7E0   // motor beyni fiziksel adresi
#define OBD_RESP_ID     0x7E8
#define OBD_PERIOD_MS   40      // istekler arası süre

// ---- Yakıt seviyesi ----
// Kangoo'da yakıt şamandırası büyük ihtimalle doğrudan orijinal göstergeye
// bağlı ve CAN'de olmayabilir. 1 yaparsanız şamandıra hattının gerilimi
// ESP32'nin ADC'sinden okunur (yüksek dirençli bölücü ile, bkz. README).
#define USE_FUEL_ADC    0
#define FUEL_ADC_PIN    34
#define FUEL_ADC_EMPTY  3000    // depo boşken okunan ham ADC değeri (ölçün)
#define FUEL_ADC_FULL   600     // depo doluyken okunan ham ADC değeri (ölçün)

// Kangoo hattı bu kadar süre sessiz kalırsa kontak kapalı sayılır,
// BMW göstergesine gönderim durur ve gösterge uyku moduna geçer.
#define BUS_TIMEOUT_MS  1500

// Dinleme modundan normal moda geçmeden önce alınması gereken düzgün çerçeve sayısı
#define FRAMES_BEFORE_TX 200
