"""UART timing and bus shims for the host GNSS parser regressions."""

import gps_parser_stream_experiment as base

ROOT, LIB = base.ROOT, base.LIB

ARDUINO = base.ARDUINO.replace(
    "inline unsigned long fixture_ms = 0;\n"
    "inline unsigned long millis() { return fixture_ms; }\n"
    "inline void delay(unsigned long ms) { fixture_ms += ms; }",
    "inline uint64_t fixture_us = 0;\n"
    "inline uint64_t first_library_delay_us = UINT64_MAX;\n"
    "inline unsigned long millis() { return uint32_t(fixture_us / 1000u); }\n"
    "inline void delay(unsigned long ms) {\n"
    "  if (first_library_delay_us == UINT64_MAX) first_library_delay_us = fixture_us;\n"
    "  fixture_us += uint64_t(ms) * 1000u;\n"
    "}",
).replace(
    "virtual size_t write(uint8_t) { return 1; }",
    "virtual size_t write(uint8_t) { return 1; }\n"
    "  virtual size_t write(const uint8_t *bytes, size_t size) {\n"
    "    size_t n = 0; while (n < size && write(bytes[n])) ++n; return n;\n"
    "  }",
).replace("class Stream : public Print {};", r"""
class Stream : public Print {
public:
  virtual int available() { return 0; }
  virtual int read() { return -1; }
  // Only one-byte reads after available()>0 occur here. This external shim is
  // not Arduino timedRead, a UART ISR, nor a transport timeout implementation.
  size_t readBytes(uint8_t *data, size_t length) {
    size_t n = 0;
    while (n < length) {
      int value = read();
      if (value < 0) break;
      data[n++] = uint8_t(value);
    }
    return n;
  }
};
""")

WIRE = r"""
#pragma once
#include <Arduino.h>
class TwoWire {
public:
  void begin() { std::abort(); }
  void beginTransmission(uint8_t) { std::abort(); }
  uint8_t endTransmission(bool = true) { std::abort(); }
  uint8_t requestFrom(uint8_t, uint8_t) { std::abort(); }
  size_t write(uint8_t) { std::abort(); }
  size_t write(const uint8_t *, size_t) { std::abort(); }
  int read() { std::abort(); }
};
inline TwoWire Wire;
"""
SPI = r"""
#pragma once
#include <Arduino.h>
constexpr uint8_t MSBFIRST = 1, SPI_MODE0 = 0;
class SPISettings {
public:
  SPISettings() = default;
  SPISettings(uint32_t, uint8_t, uint8_t) {}
};
class SPIClass {
public:
  void begin() { std::abort(); }
  void beginTransaction(const SPISettings&) { std::abort(); }
  void endTransaction() { std::abort(); }
  uint8_t transfer(uint8_t) { std::abort(); }
};
inline SPIClass SPI;
"""
