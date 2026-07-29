#ifndef RESET_CAUSE_H
#define RESET_CAUSE_H

#include <stdbool.h>
#include <stdint.h>

/* STM32WL RCC->CSR reset-flag bits. Keep these source-visible so the pure host
 * test exercises the same priority decoder as the embedded image. main.cpp
 * statically checks them against the vendor CMSIS definitions. */
#define STRATO_RCC_CSR_OBLRSTF  (1u << 25)
#define STRATO_RCC_CSR_PINRSTF  (1u << 26)
#define STRATO_RCC_CSR_BORRSTF  (1u << 27)
#define STRATO_RCC_CSR_SFTRSTF  (1u << 28)
#define STRATO_RCC_CSR_IWDGRSTF (1u << 29)
#define STRATO_RCC_CSR_WWDGRSTF (1u << 30)
#define STRATO_RCC_CSR_LPWRRSTF (1u << 31)

typedef enum {
    RESET_CAUSE_UNKNOWN = 0,
    RESET_CAUSE_WATCHDOG = 1,
    RESET_CAUSE_SOFTWARE = 2,
    RESET_CAUSE_LOW_POWER_OR_OPTION = 3,
    RESET_CAUSE_POWER_ON = 4,
    RESET_CAUSE_BROWNOUT = 5,
    RESET_CAUSE_NRST_PIN = 6,
} reset_cause_code_t;

/* Decode flags in mission-priority order. A healthy STM32WL power-on commonly
 * raises BORRSTF and PINRSTF together. Retained-session validity is the
 * stronger discriminator: BOR with a valid TAMP session means VDD dipped but
 * the backup domain survived, whereas no retained session is a cold start. */
uint8_t reset_cause_decode(uint32_t csr, bool retained_session_valid);

#endif
