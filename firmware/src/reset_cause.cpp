#include "reset_cause.h"

uint8_t reset_cause_decode(uint32_t csr, bool retained_session_valid) {
    if (csr & (STRATO_RCC_CSR_IWDGRSTF | STRATO_RCC_CSR_WWDGRSTF)) {
        return RESET_CAUSE_WATCHDOG;
    }
    if (csr & STRATO_RCC_CSR_SFTRSTF) {
        return RESET_CAUSE_SOFTWARE;
    }
    if (csr & (STRATO_RCC_CSR_LPWRRSTF | STRATO_RCC_CSR_OBLRSTF)) {
        return RESET_CAUSE_LOW_POWER_OR_OPTION;
    }
    if (csr & STRATO_RCC_CSR_BORRSTF) {
        return retained_session_valid
            ? RESET_CAUSE_BROWNOUT : RESET_CAUSE_POWER_ON;
    }
    if (csr & STRATO_RCC_CSR_PINRSTF) {
        return RESET_CAUSE_NRST_PIN;
    }
    return RESET_CAUSE_UNKNOWN;
}
