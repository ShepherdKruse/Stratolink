/**
 * Stratolink 5-second PDM audio capture via SPI (RXONLY).
 *
 * Uses SPI1 in receive-only master mode for a continuous, gap-free
 * PDM clock. Every bit is captured in lock-step.
 *
 *   PB3 = SPI1_SCK  (AF5) -> T3902 CLK at 3.0 MHz, 50% duty
 *   PB4 = SPI1_MISO (AF5) -> T3902 DATA input
 *
 * CPOL=0, CPHA=0: data sampled on rising edge.
 * T3902 RIGHT channel (SELECT=GND) drives data on falling edge;
 * data is stable at the next rising edge (166 ns settling at 3 MHz).
 *
 * Decimates to 9375 Hz 8-bit PCM (320 PDM bits / 40 SPI bytes per sample).
 * Nyquist = 4687 Hz — captures speech clearly.
 *
 * Usage:
 *   1. Copy this file to src/main.cpp
 *   2. pio run -t upload
 *   3. Run: python test/capture_audio.py
 *   4. Restore flight firmware: copy src/main.cpp.flight to src/main.cpp
 */
#include <Arduino.h>
#include "stratolink_pins.h"

// SPI1 at 48 MHz / 16 = 3.0 MHz (T3902 spec: 1.0 - 3.25 MHz)
#define PDM_CLOCK_HZ    3000000
#define SAMPLE_RATE     9375
#define DURATION_SEC    5
#define TOTAL_SAMPLES   (SAMPLE_RATE * DURATION_SEC)    // 46875
#define DECIMATION      (PDM_CLOCK_HZ / SAMPLE_RATE)    // 320
#define BYTES_PER_SAMPLE (DECIMATION / 8)               // 40
#define SKIP_SAMPLES    18750 // discard first 2 s for mic transient + settling

#define CAPTURE_MAGIC   0x41554449u  // "AUDI"

struct __attribute__((packed)) CaptureHeader {
    uint32_t magic;
    uint32_t sample_rate;
    uint32_t total_samples;
    uint32_t samples_captured;
    uint8_t  capture_done;
    uint8_t  _pad[3];
};

volatile CaptureHeader hdr __attribute__((used)) = {
    CAPTURE_MAGIC, SAMPLE_RATE, TOTAL_SAMPLES, 0, 0, {0}
};
volatile uint8_t audio_buf[TOTAL_SAMPLES] __attribute__((used, section(".noinit")));

static inline uint8_t popcount8(uint8_t v) {
    v = v - ((v >> 1) & 0x55);
    v = (v & 0x33) + ((v >> 2) & 0x33);
    return (v + (v >> 4)) & 0x0F;
}

static inline uint8_t spi_read_byte(void) {
    while (!(SPI1->SR & SPI_SR_RXNE));
    return *(volatile uint8_t *)&SPI1->DR;
}

void setup() {
    // Enable peripheral clocks
    RCC->AHB2ENR  |= RCC_AHB2ENR_GPIOBEN;
    RCC->APB2ENR  |= RCC_APB2ENR_SPI1EN;
    __DSB();

    // PB3 -> SPI1_SCK (AF5): alternate function, very high speed
    GPIOB->MODER   = (GPIOB->MODER   & ~(3u << 6))  | (2u << 6);
    GPIOB->AFR[0]  = (GPIOB->AFR[0]  & ~(0xFu << 12)) | (5u << 12);
    GPIOB->OSPEEDR = (GPIOB->OSPEEDR & ~(3u << 6))  | (3u << 6);
    GPIOB->PUPDR   = (GPIOB->PUPDR   & ~(3u << 6));

    // PB4 -> SPI1_MISO (AF5): alternate function, no pull
    GPIOB->MODER   = (GPIOB->MODER   & ~(3u << 8))  | (2u << 8);
    GPIOB->AFR[0]  = (GPIOB->AFR[0]  & ~(0xFu << 16)) | (5u << 16);
    GPIOB->PUPDR   = (GPIOB->PUPDR   & ~(3u << 8));

    // SPI1: master, RXONLY, 48 MHz / 16 = 3 MHz, CPOL=0 CPHA=0
    SPI1->CR1 = 0;
    SPI1->CR1 = SPI_CR1_MSTR
              | SPI_CR1_RXONLY
              | (3u << 3)           // BR = 011 -> /16
              | SPI_CR1_SSM
              | SPI_CR1_SSI;
    SPI1->CR2 = (7u << 8)          // DS = 0111 -> 8-bit
              | SPI_CR2_FRXTH;      // RXNE on 8 bits

    // Start continuous clock
    SPI1->CR1 |= SPI_CR1_SPE;

    // Mic wake-up + transient skip: drain 500 ms of PDM data.
    // T3902 needs >= 20 ms clock to exit sleep, plus settling time
    // for the sigma-delta modulator to stabilize.
    for (uint32_t s = 0; s < SKIP_SAMPLES; s++) {
        for (uint16_t b = 0; b < BYTES_PER_SAMPLE; b++) {
            (void)spi_read_byte();
        }
    }

    // Capture
    for (uint32_t s = 0; s < TOTAL_SAMPLES; s++) {
        uint16_t ones = 0;
        for (uint16_t b = 0; b < BYTES_PER_SAMPLE; b++) {
            ones += popcount8(spi_read_byte());
        }
        audio_buf[s] = (uint8_t)((uint32_t)ones * 255 / DECIMATION);
        hdr.samples_captured = s + 1;
    }

    // Stop
    SPI1->CR1 &= ~SPI_CR1_SPE;
    RCC->APB2ENR &= ~RCC_APB2ENR_SPI1EN;

    hdr.capture_done = 0xAA;
}

void loop() { delay(1000); }
