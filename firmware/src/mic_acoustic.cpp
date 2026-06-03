/**
 * T3902 PDM microphone - stratospheric acoustic event detection.
 *
 * SPI1 RXONLY master generates a continuous 3 MHz clock on PB3; PDM data
 * streams in on PB4.  Firmware decimates to ~9375 Hz PCM, computes the
 * DC-blocked variance of the ones-count in one streaming pass (no buffer),
 * and compares it against an adaptive noise floor.  At stratospheric
 * altitude the ambient floor is near-zero, so any aircraft / rocket / drone
 * signature stands out cleanly.
 *
 * Detection cycle: 50 ms wake + 213 ms skip + 55 ms capture ~ 318 ms.
 */
#include "mic_acoustic.h"
#include "stratolink_pins.h"
#include <Arduino.h>

/* ---- PDM / decimation parameters ---- */
#define SPI_PRESCALER_BR     3       /* BR[2:0] = 011 -> 48 MHz / 16 = 3 MHz   */
#define BYTES_PER_SAMPLE     40      /* 320 PDM bits -> 9375 Hz PCM             */

/* ---- Capture geometry ---- */
#define WAKEUP_BYTES         18750   /* 50 ms of clock at 375 kB/s             */
#define SKIP_SAMPLES         2000    /* 213 ms transient rejection             */
#define CAPTURE_SAMPLES      512     /* 55 ms analysis window                  */

/* ---- Detection tuning ---- */
#define THRESHOLD_MULT_SQ    16      /* 4x RMS above noise floor  (4^2 = 16)    */
#define NOISE_EMA_SHIFT      4       /* noise-floor EMA weight = 1/16          */

static bool     inited = false;
static uint32_t noise_floor_sq = 16; /* seed for the x16 DC-blocked variance scale */

static inline uint8_t popcount8(uint8_t v) {
    v = v - ((v >> 1) & 0x55);
    v = (v & 0x33) + ((v >> 2) & 0x33);
    return (v + (v >> 4)) & 0x0F;
}

/* ------------------------------------------------------------------ */
bool mic_acoustic_init(void) {
    RCC->AHB2ENR  |= RCC_AHB2ENR_GPIOBEN;
    RCC->APB2ENR  |= RCC_APB2ENR_SPI1EN;
    __DSB();

    /* PB3 -> SPI1_SCK  (AF5), very-high speed */
    GPIOB->MODER   = (GPIOB->MODER   & ~(3u << 6))  | (2u << 6);
    GPIOB->AFR[0]  = (GPIOB->AFR[0]  & ~(0xFu << 12)) | (5u << 12);
    GPIOB->OSPEEDR = (GPIOB->OSPEEDR & ~(3u << 6))  | (3u << 6);

    /* PB4 -> SPI1_MISO (AF5) */
    GPIOB->MODER   = (GPIOB->MODER   & ~(3u << 8))  | (2u << 8);
    GPIOB->AFR[0]  = (GPIOB->AFR[0]  & ~(0xFu << 16)) | (5u << 16);

    /* SPI1: master, RXONLY, 3 MHz, CPOL=0 CPHA=0, 8-bit, FRXTH */
    SPI1->CR1 = SPI_CR1_MSTR | SPI_CR1_RXONLY
              | (SPI_PRESCALER_BR << 3)
              | SPI_CR1_SSM | SPI_CR1_SSI;
    SPI1->CR2 = (7u << 8) | (1u << 12);

    inited = true;
    return true;
}

/* ------------------------------------------------------------------ */
/* Bounded SPI RXNE wait. Returns false on timeout so a missing/dead mic
 * (or PB3/PB4 routing issue) can't deadlock the main telemetry loop. */
static inline bool spi_wait_rxne(uint32_t timeout_ms) {
    uint32_t deadline = millis() + timeout_ms;
    while (!(SPI1->SR & SPI_SR_RXNE)) {
        if ((int32_t)(millis() - deadline) >= 0) return false;
    }
    return true;
}

bool mic_acoustic_detect(uint8_t* acoustic_event) {
    if (!acoustic_event) return false;
    *acoustic_event = 0;
    if (!inited) return false;

    volatile uint8_t* dr = (volatile uint8_t*)&SPI1->DR;

    /* --- start clock, wake mic --- */
    SPI1->CR1 |= SPI_CR1_SPE;

    /* wake-up: 50 ms of continuous clock - bail if mic never responds */
    for (uint32_t i = 0; i < WAKEUP_BYTES; i++) {
        if (!spi_wait_rxne(5)) { SPI1->CR1 &= ~SPI_CR1_SPE; return false; }
        (void)*dr;
    }

    /* skip sigma-delta transient */
    for (uint16_t s = 0; s < SKIP_SAMPLES; s++) {
        for (uint8_t b = 0; b < BYTES_PER_SAMPLE; b++) {
            if (!spi_wait_rxne(5)) { SPI1->CR1 &= ~SPI_CR1_SPE; return false; }
            (void)*dr;
        }
    }

    /* capture: accumulate the per-sample ones-count and its square (no buffer)
     * so we can compute a DC-blocked variance below. */
    uint32_t sum_ones = 0;
    uint64_t sum_ones_sq = 0;
    for (uint16_t s = 0; s < CAPTURE_SAMPLES; s++) {
        uint16_t ones = 0;
        for (uint8_t b = 0; b < BYTES_PER_SAMPLE; b++) {
            if (!spi_wait_rxne(5)) { SPI1->CR1 &= ~SPI_CR1_SPE; return false; }
            ones += popcount8(*dr);
        }
        sum_ones += ones;
        sum_ones_sq += (uint32_t)ones * ones;
    }

    /* --- stop clock, mic enters sleep after 1 ms --- */
    SPI1->CR1 &= ~SPI_CR1_SPE;
    (void)SPI1->DR;
    (void)SPI1->SR;

    /* --- detection logic ---
     * DC-blocked variance of the ones-count: var = (N*sum_sq - sum^2)/N^2,
     * scaled x16 for integer resolution.  Removes the mic's idle-offset
     * pedestal (real idle density ~50.5%, not the assumed 50%), which the old
     * fixed PDM_CENTER=160 left in rms_sq - a pedestal that DRIFTS with
     * temperature and was a prime suspect for the flight-1 false acoustic
     * events.  Bench-validated on board #2 (2026-06-03): tone/silence margin
     * 28x -> 233x, 0 false-positives, flat vs temperature.  (A proper sinc^4
     * audio-fidelity decode is a separate, larger change, not needed for this
     * 1-bit energy detector - see analysis/acoustic/03_bench_session1.md.) */
    uint64_t num = (uint64_t)CAPTURE_SAMPLES * sum_ones_sq
                 - (uint64_t)sum_ones * sum_ones;
    uint32_t rms_sq = (uint32_t)((num * 16u) / ((uint64_t)CAPTURE_SAMPLES * CAPTURE_SAMPLES));

    /* adapt noise floor only when signal looks quiet */
    if (rms_sq < noise_floor_sq * 2) {
        noise_floor_sq += ((int32_t)rms_sq - (int32_t)noise_floor_sq)
                          >> NOISE_EMA_SHIFT;
        if (noise_floor_sq < 1) noise_floor_sq = 1;
    }

    if (rms_sq > noise_floor_sq * THRESHOLD_MULT_SQ)
        *acoustic_event = 1;

    return true;
}
