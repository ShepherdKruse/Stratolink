#ifndef SENSOR_LTR390_H
#define SENSOR_LTR390_H

#include <stdint.h>
#include <stdbool.h>

bool sensor_ltr390_init(void);
bool sensor_ltr390_read_uv_index(uint8_t* uv_index);
bool sensor_ltr390_read_ambient_lux(uint16_t* lux);

#endif /* SENSOR_LTR390_H */
