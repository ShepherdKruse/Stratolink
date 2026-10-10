"""Arduino shims shared by the host GNSS parser regressions."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "firmware/.pio/libdeps/stratolink/SparkFun u-blox GNSS v3/src"

ARDUINO = r"""
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdlib>
#include <cmath>
#include <algorithm>
#include <string>
using String = std::string;
// Match the embedded C library's strstr return type; parser does not call it.
inline char *embedded_strstr(const char *s, const char *p) {
  return const_cast<char *>(std::strstr(s, p));
}
#define strstr embedded_strstr
using std::min;
using std::max;
class __FlashStringHelper;
#define F(s) reinterpret_cast<const __FlashStringHelper *>(s)
#define OUTPUT 1
#define HIGH 1
#define LOW 0
#define HEX 16
inline unsigned long fixture_ms = 0;
inline unsigned long millis() { return fixture_ms; }
inline void delay(unsigned long ms) { fixture_ms += ms; }
inline void pinMode(uint8_t, int) {}
inline void digitalWrite(uint8_t, int) {}
class Print {
public:
  virtual ~Print() = default;
  virtual size_t write(uint8_t) { return 1; }
  template<class... T> void print(T...) {}
  template<class... T> void println(T...) {}
};
class Stream : public Print {};
inline Stream Serial;
"""
