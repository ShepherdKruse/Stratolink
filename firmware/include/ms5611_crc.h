#ifndef MS5611_CRC_H
#define MS5611_CRC_H

#include <stdbool.h>
#include <stdint.h>

/**
 * Validate the CRC4 stored in an MS5611's complete eight-word PROM.
 *
 * The factory CRC is the low nibble of word 7. The calculation follows
 * the algorithm in the MS5611 datasheet and does not modify the caller's
 * PROM buffer.
 */
bool ms5611_prom_crc_valid(const uint16_t prom[8]);

#endif /* MS5611_CRC_H */
