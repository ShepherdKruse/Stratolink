#include <assert.h>
#include <stdio.h>

#include "reset_cause.h"

int main(void) {
    assert(reset_cause_decode(0, false) == RESET_CAUSE_UNKNOWN);
    assert(reset_cause_decode(STRATO_RCC_CSR_PINRSTF, false) ==
           RESET_CAUSE_NRST_PIN);
    assert(reset_cause_decode(STRATO_RCC_CSR_BORRSTF |
                              STRATO_RCC_CSR_PINRSTF, false) ==
           RESET_CAUSE_POWER_ON);
    assert(reset_cause_decode(STRATO_RCC_CSR_BORRSTF |
                              STRATO_RCC_CSR_PINRSTF, true) ==
           RESET_CAUSE_BROWNOUT);
    assert(reset_cause_decode(STRATO_RCC_CSR_BORRSTF, false) ==
           RESET_CAUSE_POWER_ON);
    assert(reset_cause_decode(STRATO_RCC_CSR_BORRSTF, true) ==
           RESET_CAUSE_BROWNOUT);
    assert(reset_cause_decode(STRATO_RCC_CSR_OBLRSTF |
                              STRATO_RCC_CSR_BORRSTF, true) ==
           RESET_CAUSE_LOW_POWER_OR_OPTION);
    assert(reset_cause_decode(STRATO_RCC_CSR_LPWRRSTF |
                              STRATO_RCC_CSR_SFTRSTF, true) ==
           RESET_CAUSE_SOFTWARE);
    assert(reset_cause_decode(STRATO_RCC_CSR_IWDGRSTF |
                              STRATO_RCC_CSR_SFTRSTF, true) ==
           RESET_CAUSE_WATCHDOG);
    assert(reset_cause_decode(STRATO_RCC_CSR_WWDGRSTF |
                              STRATO_RCC_CSR_IWDGRSTF, false) ==
           RESET_CAUSE_WATCHDOG);
    puts("reset-cause priority and retained-domain classification passed");
    return 0;
}
