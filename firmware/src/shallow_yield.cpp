#include <Arduino.h>

/*
 * STM32duino's framework yield() is a weak empty hook, and delay() calls it
 * repeatedly until SysTick advances. Without an application override, every
 * driver/retry/conversion delay busy-spins the Cortex-M4. This is especially
 * material in the SparkFun GNSS library, whose explicit PVT request waits can
 * occupy much of a bounded 30-second acquisition.
 *
 * Use ordinary CPU SLEEP between interrupts. This is deliberately not
 * STOP1/STOP2: SysTick, UART, I2C, radio DIO, and EXTI remain clocked and wake
 * the core. Clear SLEEPDEEP on every entry so a delay cannot inherit a stale
 * deep-sleep bit from any prior power-management path.
 */
extern "C" void yield(void) {
#if defined(ARDUINO_ARCH_STM32)
    SCB->SCR &= ~SCB_SCR_SLEEPDEEP_Msk;
    __DSB();
    __WFI();
    __ISB();
#endif
}
