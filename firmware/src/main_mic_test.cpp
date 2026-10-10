/* Microphone bench-capture diagnostic (T3902 PDM mic, MK1).
 *
 * Purpose: get the RAW waveform off the mic over J-Link so we can design and
 * validate the acoustic DSP on the laptop instead of trusting the 1-bit
 * in-flight detector.  Self-contained like main_gps_diag.cpp (no LoRa/GPS/IWDG)
 * so a minimal build can't wedge.
 *
 * Each cycle it: drives SPI1 RXONLY @3 MHz on PB3(SCK)/PB4(PDM), skips the
 * sigma-delta transient, then in ONE pass fills
 *   - pcm_buf[]  : N_PCM decoded PCM samples (firmware's sinc^1 decimation,
 *                  ones-per-320-bits minus 160) @ 9375 Hz, and
 *   - pdm_buf[]  : the first N_PDM raw PDM bytes (3 MHz bitstream) so the host
 *                  can re-decimate properly (sinc^4 / FIR + DC block) offline,
 * and replays the production detector (rms_sq vs adaptive noise floor) so we
 * can watch `event` live.  Header `mt` carries seq + results; bump of mt.seq
 * AFTER the buffers are written signals "frame ready" to the host poller.
 *
 * Read over J-Link (addresses from `arm-none-eabi-nm firmware.elf`):
 *   mem32 <&mt> 8           # header (magic 0x6D696354 = 'micT')
 *   savebin pcm.bin <&pcm_buf> 12288     # N_PCM*2
 *   savebin pdm.bin <&pdm_buf> 8192      # N_PDM
 * Host harness automates this: analysis/acoustic/mic_bench.py
 */
#include <Arduino.h>
#include "stratolink_pins.h"
#include "config.h"

/* ---- capture geometry (mirror mic_acoustic.cpp) ---- */
#define SPI_PRESCALER_BR  3       /* 48 MHz / 16 = 3 MHz SCK                  */
#define BYTES_PER_SAMPLE  40      /* 320 PDM bits -> 9375 Hz PCM              */
#define PDM_CENTER        160     /* 320 / 2                                  */
#define WAKEUP_BYTES      18750   /* 50 ms wake-up clock                      */
#define SKIP_SAMPLES      2000    /* 213 ms transient reject                  */
#define SAMPLE_RATE_HZ    9375

#define N_PCM             6144    /* ~0.655 s window  (12 KB)                 */
#define N_PDM             24576   /* raw PDM snippet bytes (~65 ms)  (24 KB)  */

/* ---- detector tuning (mirror mic_acoustic.cpp) ---- */
#define THRESHOLD_MULT_SQ 16
#define NOISE_EMA_SHIFT   4

typedef struct {
    uint32_t magic;        /* 0x6D696354 'micT'                              */
    uint32_t seq;          /* ++ after each frame is fully written           */
    uint32_t n_pcm;        /* samples in pcm_buf                             */
    uint32_t n_pdm;        /* bytes in pdm_buf                               */
    uint32_t sr_hz;        /* PCM sample rate                                */
    uint32_t rms_sq;       /* mean-square, fixed centre 160 (CURRENT firmware) */
    uint32_t rms_sq_var;   /* DC-blocked variance of ones-count (PROPOSED)   */
    uint32_t noise_floor_sq;
    uint32_t event;        /* 1 if rms_sq > floor * THRESHOLD_MULT_SQ        */
    uint32_t err;          /* 0 ok; 1 mic timeout (no RXNE)                  */
    uint32_t uptime_s;
} mic_test_t;

volatile mic_test_t mt = { 0x6D696354, 0, N_PCM, N_PDM, SAMPLE_RATE_HZ, 0, 0, 16, 0, 0, 0 };
int16_t  pcm_buf[N_PCM];
uint8_t  pdm_buf[N_PDM];

static inline uint8_t popcount8(uint8_t v) {
    v = v - ((v >> 1) & 0x55);
    v = (v & 0x33) + ((v >> 2) & 0x33);
    return (v + (v >> 4)) & 0x0F;
}

static void mic_spi_init(void) {
    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOBEN;
    RCC->APB2ENR |= RCC_APB2ENR_SPI1EN;
    __DSB();
    /* PB3 -> SPI1_SCK (AF5), very-high speed */
    GPIOB->MODER   = (GPIOB->MODER   & ~(3u << 6))   | (2u << 6);
    GPIOB->AFR[0]  = (GPIOB->AFR[0]  & ~(0xFu << 12)) | (5u << 12);
    GPIOB->OSPEEDR = (GPIOB->OSPEEDR & ~(3u << 6))   | (3u << 6);
    /* PB4 -> SPI1_MISO (AF5) */
    GPIOB->MODER  = (GPIOB->MODER  & ~(3u << 8))   | (2u << 8);
    GPIOB->AFR[0] = (GPIOB->AFR[0] & ~(0xFu << 16)) | (5u << 16);
    /* master, RXONLY, 3 MHz, mode0, 8-bit, FRXTH */
    SPI1->CR1 = SPI_CR1_MSTR | SPI_CR1_RXONLY | (SPI_PRESCALER_BR << 3)
              | SPI_CR1_SSM | SPI_CR1_SSI;
    SPI1->CR2 = (7u << 8) | (1u << 12);
}

static inline bool spi_wait_rxne(uint32_t timeout_ms) {
    uint32_t deadline = millis() + timeout_ms;
    while (!(SPI1->SR & SPI_SR_RXNE)) {
        if ((int32_t)(millis() - deadline) >= 0) return false;
    }
    return true;
}

/* Capture one window into pcm_buf[] (+ raw into pdm_buf[]); returns false on
 * mic timeout.  Accumulates sum_sq (fixed-centre, current firmware) AND the
 * ones-count sums so loop() can also compute the DC-blocked variance. */
static bool capture_window(uint64_t* sum_sq_out, uint64_t* sum_ones_out,
                           uint64_t* sum_ones_sq_out) {
    volatile uint8_t* dr = (volatile uint8_t*)&SPI1->DR;
    SPI1->CR1 |= SPI_CR1_SPE;

    for (uint32_t i = 0; i < WAKEUP_BYTES; i++) {           /* wake-up clock */
        if (!spi_wait_rxne(5)) { SPI1->CR1 &= ~SPI_CR1_SPE; return false; }
        (void)*dr;
    }
    for (uint16_t s = 0; s < SKIP_SAMPLES; s++) {            /* skip transient */
        for (uint8_t b = 0; b < BYTES_PER_SAMPLE; b++) {
            if (!spi_wait_rxne(5)) { SPI1->CR1 &= ~SPI_CR1_SPE; return false; }
            (void)*dr;
        }
    }
    uint64_t sum_sq = 0, sum_ones = 0, sum_ones_sq = 0;
    uint32_t pdm_i = 0;
    for (uint16_t s = 0; s < N_PCM; s++) {
        uint16_t ones = 0;
        for (uint8_t b = 0; b < BYTES_PER_SAMPLE; b++) {
            if (!spi_wait_rxne(5)) { SPI1->CR1 &= ~SPI_CR1_SPE; return false; }
            uint8_t v = *dr;
            if (pdm_i < N_PDM) pdm_buf[pdm_i++] = v;        /* raw snippet */
            ones += popcount8(v);
        }
        int16_t pcm = (int16_t)ones - PDM_CENTER;
        pcm_buf[s] = pcm;
        sum_sq += (uint32_t)((int32_t)pcm * pcm);
        sum_ones += ones;
        sum_ones_sq += (uint32_t)ones * ones;
    }
    SPI1->CR1 &= ~SPI_CR1_SPE;
    (void)SPI1->DR; (void)SPI1->SR;
    *sum_sq_out = sum_sq; *sum_ones_out = sum_ones; *sum_ones_sq_out = sum_ones_sq;
    return true;
}

void setup() {
    mic_spi_init();
}

void loop() {
    uint64_t sum_sq = 0, sum_ones = 0, sum_ones_sq = 0;
    bool ok = capture_window(&sum_sq, &sum_ones, &sum_ones_sq);
    if (!ok) { mt.err = 1; mt.seq++; delay(300); return; }
    mt.err = 0;

    uint32_t rms_sq = (uint32_t)(sum_sq / N_PCM);
    /* DC-blocked variance of the ones-count: var = (N*sum_sq - sum^2)/N^2,
     * scaled x16 to keep integer resolution on the sub-unity silent floor.
     * Removes the temperature-drifting idle-offset pedestal the fixed
     * PDM_CENTER=160 leaves in rms_sq. */
    uint64_t num = (uint64_t)N_PCM * sum_ones_sq - sum_ones * sum_ones;
    uint32_t rms_var = (uint32_t)((num * 16u) / ((uint64_t)N_PCM * N_PCM));
    mt.rms_sq = rms_sq;
    mt.rms_sq_var = rms_var;
    /* PROPOSED detector: adaptive floor + threshold on the DC-blocked variance
     * (not the fixed-centre mean-square). */
    if (rms_var < mt.noise_floor_sq * 2) {
        mt.noise_floor_sq += ((int32_t)rms_var - (int32_t)mt.noise_floor_sq) >> NOISE_EMA_SHIFT;
        if (mt.noise_floor_sq < 1) mt.noise_floor_sq = 1;
    }
    mt.event = (rms_var > mt.noise_floor_sq * THRESHOLD_MULT_SQ) ? 1u : 0u;
    mt.uptime_s = millis() / 1000u;

    __DSB();
    mt.seq++;          /* publish: buffers are coherent, host may read now */
    delay(300);        /* dwell so the host can grab a stable frame */
}
