/**
 * Stratolink board validation firmware.
 *
 * Tests all components: I2C sensors, LTR-390UV, power ADC, GPS UART,
 * GPIO pins, and T3902 PDM microphone.
 *
 * Usage:
 *   1. Copy this file to src/main.cpp
 *   2. pio run -t upload
 *   3. Run: python test/decode_results.py (reads results via J-Link)
 *   4. Restore flight firmware: copy src/main.cpp.flight to src/main.cpp
 *
 * Results are stored in a packed struct at a fixed RAM address.
 * The decode script reads them via J-Link and prints a report.
 */
#include <Arduino.h>
#include <Wire.h>
#include "stratolink_pins.h"
#include "sensor_ms5611.h"
#include "sensor_tmp117.h"
#include "sensor_lis2dh12.h"
#include "power_adc.h"

#define LTR390_ADDR       0x53
#define LTR390_PART_ID    0x06
#define LTR390_MAIN_CTRL  0x00

static uint8_t ltr390_read_reg(uint8_t reg) {
    Wire.beginTransmission(LTR390_ADDR);
    Wire.write(reg);
    Wire.endTransmission();
    Wire.requestFrom((int)LTR390_ADDR, 1);
    return Wire.available() ? Wire.read() : 0xFF;
}

struct __attribute__((packed)) TestResults {
    uint8_t  i2c_found_count;
    uint8_t  ms5611_init_ok;
    uint8_t  lis2dh12_init_ok;
    uint8_t  tmp117_init_ok;
    uint16_t baro_pressure_ch;
    int16_t  baro_temp_cd;
    int16_t  tmp117_temp_cd;
    int16_t  accel_x;
    int16_t  accel_y;
    int16_t  accel_z;
    uint8_t  baro_read_ok;
    uint8_t  baro_temp_ok;
    uint8_t  tmp117_read_ok;
    uint8_t  accel_read_ok;
    uint8_t  ltr390_part_id;
    uint8_t  ltr390_als_enabled;
    uint32_t ltr390_als_data;
    uint8_t  ltr390_uv_enabled;
    uint32_t ltr390_uv_data;
    uint16_t vstor_mv;
    uint16_t solar_mv;
    uint8_t  vbat_ok;
    uint8_t  power_tier;
    uint8_t  gps_uart_bytes;
    uint8_t  gps_reset_n;
    uint8_t  accel_int1;
    uint8_t  spare_pa1;
    uint8_t  spare_pa9;
    uint8_t  spare_pb2;
    uint8_t  mic_static_data;
    uint8_t  mic_clk_readback;
    uint16_t mic_ones_fast;
    uint16_t mic_ones_paced;
    uint16_t mic_ones_extended;
    uint16_t mic_total_bits;
    uint8_t  mic_alive;
    uint8_t  phase;
    uint8_t  done;
};

volatile TestResults test __attribute__((used)) = {0};

static void mic_start_clock(void) {
    RCC->APB1ENR1 |= RCC_APB1ENR1_TIM2EN;
    __DSB();
    GPIOB->MODER   = (GPIOB->MODER   & ~(3u << 6)) | (2u << 6);
    GPIOB->AFR[0]  = (GPIOB->AFR[0]  & ~(0xFu << 12)) | (1u << 12);
    GPIOB->OSPEEDR = (GPIOB->OSPEEDR & ~(3u << 6)) | (2u << 6);
    TIM2->CR1  = 0;
    TIM2->PSC  = 0;
    TIM2->ARR  = 19;
    TIM2->CCR2 = 10;
    TIM2->CCMR1 = (6u << 12) | TIM_CCMR1_OC2PE;
    TIM2->CCER  = TIM_CCER_CC2E;
    TIM2->EGR   = TIM_EGR_UG;
    TIM2->CR1   = TIM_CR1_CEN;
}

static void mic_stop_clock(void) {
    TIM2->CR1  = 0;
    TIM2->CCER = 0;
    RCC->APB1ENR1 &= ~RCC_APB1ENR1_TIM2EN;
    GPIOB->MODER = (GPIOB->MODER & ~(3u << 6)) | (1u << 6);
    GPIOB->BSRR  = (1u << (3 + 16));
}

void setup() {
    Wire.setSDA(PIN_I2C_SDA);
    Wire.setSCL(PIN_I2C_SCL);
    Wire.begin();
    Wire.setClock(100000);

    // Phase 1: I2C scan
    test.phase = 1;
    const uint8_t addrs[] = {0x18, 0x42, 0x48, 0x53, 0x76};
    uint8_t found = 0;
    for (uint8_t i = 0; i < sizeof(addrs); i++) {
        Wire.beginTransmission(addrs[i]);
        if (Wire.endTransmission() == 0) found++;
    }
    test.i2c_found_count = found;

    // Phase 2: driver init
    test.phase = 2;
    test.ms5611_init_ok   = sensor_ms5611_init() ? 1 : 0;
    test.lis2dh12_init_ok = sensor_lis2dh12_init() ? 1 : 0;
    test.tmp117_init_ok   = sensor_tmp117_init() ? 1 : 0;

    // Phase 3: sensor reads
    test.phase = 3;
    uint16_t pres = 0;
    test.baro_read_ok = sensor_ms5611_read_pressure_centihpa(&pres) ? 1 : 0;
    test.baro_pressure_ch = pres;
    int16_t btemp = 0;
    test.baro_temp_ok = sensor_ms5611_read_temp_centidegrees(&btemp) ? 1 : 0;
    test.baro_temp_cd = btemp;
    int16_t ttemp = 0;
    test.tmp117_read_ok = sensor_tmp117_read_centidegrees(&ttemp) ? 1 : 0;
    test.tmp117_temp_cd = ttemp;
    int16_t ax = 0, ay = 0, az = 0;
    test.accel_read_ok = sensor_lis2dh12_read_accel_cm_s2(&ax, &ay, &az) ? 1 : 0;
    test.accel_x = ax; test.accel_y = ay; test.accel_z = az;

    // Phase 4: LTR-390UV
    test.phase = 4;
    test.ltr390_part_id = ltr390_read_reg(LTR390_PART_ID);
    Wire.beginTransmission(LTR390_ADDR);
    Wire.write(LTR390_MAIN_CTRL);
    Wire.write(0x02);
    if (Wire.endTransmission() == 0) {
        test.ltr390_als_enabled = 1;
        delay(100);
        test.ltr390_als_data = (uint32_t)ltr390_read_reg(0x0F) << 16
                             | (uint32_t)ltr390_read_reg(0x0E) << 8
                             | ltr390_read_reg(0x0D);
    }
    Wire.beginTransmission(LTR390_ADDR);
    Wire.write(LTR390_MAIN_CTRL);
    Wire.write(0x0A);
    if (Wire.endTransmission() == 0) {
        test.ltr390_uv_enabled = 1;
        delay(100);
        test.ltr390_uv_data = (uint32_t)ltr390_read_reg(0x12) << 16
                            | (uint32_t)ltr390_read_reg(0x11) << 8
                            | ltr390_read_reg(0x10);
    }

    // Phase 5: power ADC
    test.phase = 5;
    power_adc_init();
    test.vstor_mv   = power_adc_read_vSTOR_mv();
    test.solar_mv   = power_adc_read_solar_mv();
    test.power_tier = (uint8_t)power_adc_get_tier();
    pinMode(PIN_VBAT_OK, INPUT);
    test.vbat_ok = digitalRead(PIN_VBAT_OK);

    // Phase 6: GPS UART
    test.phase = 6;
    GPS_SERIAL.begin(GPS_BAUD);
    uint32_t t0 = millis();
    uint8_t rx = 0;
    while (millis() - t0 < 2000) {
        if (GPS_SERIAL.available()) { GPS_SERIAL.read(); if (rx < 255) rx++; }
    }
    test.gps_uart_bytes = rx;

    // Phase 7: GPIO
    test.phase = 7;
    pinMode(PIN_GPS_RESET_N, INPUT);
    test.gps_reset_n = digitalRead(PIN_GPS_RESET_N);
    pinMode(PIN_ACCEL_INT1, INPUT);
    test.accel_int1 = digitalRead(PIN_ACCEL_INT1);
    pinMode(PIN_SPARE_PA1, INPUT_PULLDOWN);
    pinMode(PIN_SPARE_PA9, INPUT_PULLDOWN);
    pinMode(PIN_SPARE_PB2, INPUT_PULLDOWN);
    delay(1);
    test.spare_pa1 = digitalRead(PIN_SPARE_PA1);
    test.spare_pa9 = digitalRead(PIN_SPARE_PA9);
    test.spare_pb2 = digitalRead(PIN_SPARE_PB2);

    // Phase 8: microphone (TIM2 hardware PWM clock, 2.4 MHz 50% duty)
    test.phase = 8;
    test.mic_total_bits = 2048;

    volatile uint32_t *idr = &GPIOB->IDR;
    const uint32_t data_bit = (1u << 4);

    // static line test
    pinMode(PIN_MIC_PDM_DATA, INPUT);
    pinMode(PIN_MIC_PDM_CLK, OUTPUT);
    digitalWrite(PIN_MIC_PDM_CLK, LOW);
    delay(1);
    uint8_t raw = digitalRead(PIN_MIC_PDM_DATA);
    pinMode(PIN_MIC_PDM_DATA, INPUT_PULLUP);
    delay(1);
    uint8_t pulled = digitalRead(PIN_MIC_PDM_DATA);
    test.mic_static_data = (pulled << 1) | raw;
    pinMode(PIN_MIC_PDM_DATA, INPUT);

    // clock readback
    uint8_t rb = 1;
    digitalWrite(PIN_MIC_PDM_CLK, HIGH);
    delayMicroseconds(10);
    if (digitalRead(PIN_MIC_PDM_CLK) != HIGH) rb = 0;
    digitalWrite(PIN_MIC_PDM_CLK, LOW);
    delayMicroseconds(10);
    if (digitalRead(PIN_MIC_PDM_CLK) != LOW)  rb = 0;
    test.mic_clk_readback = rb;

    // start hardware clock, wake mic
    mic_start_clock();
    delay(50);

    // fast poll: 4096 reads
    { uint16_t n = 0; for (uint16_t i = 0; i < 4096; i++) { if (*idr & data_bit) n++; } test.mic_ones_fast = n; }

    // paced poll: ~1 read per clock period
    { uint16_t n = 0; for (uint16_t i = 0; i < 2048; i++) {
        __NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();
        __NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();
        if (*idr & data_bit) n++; } test.mic_ones_paced = n; }

    // extended: 32768 reads
    { uint16_t n = 0; for (uint32_t i = 0; i < 32768; i++) { if (*idr & data_bit) { if (n < 65535) n++; } } test.mic_ones_extended = n; }

    mic_stop_clock();

    test.mic_alive = 0;
    if (test.mic_ones_fast     > 200 && test.mic_ones_fast     < 3896) test.mic_alive = 1;
    if (test.mic_ones_paced    > 100 && test.mic_ones_paced    < 1948) test.mic_alive = 1;
    if (test.mic_ones_extended > 100 && test.mic_ones_extended < 32668) test.mic_alive = 1;

    test.phase = 9;
    test.done = 0xAA;
}

void loop() { delay(1000); }
