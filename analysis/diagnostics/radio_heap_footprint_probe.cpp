/* Cross-compile with the exact flight translation-unit flags. The array
 * symbol sizes expose the ARM ABI object footprints without running target
 * code or modifying the frozen firmware inputs. */
#include <RadioLib.h>

extern "C" {
unsigned char strato_sizeof_stm32wlx[sizeof(STM32WLx)];
unsigned char strato_sizeof_stm32wlx_module[sizeof(STM32WLx_Module)];
}
