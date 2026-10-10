#pragma once

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

class GpsBoundedStream : public Stream {
public:
    explicit GpsBoundedStream(Stream& stream) : stream_(stream) {}

    void begin_position_phase() {
        position_phase_ = true;
        poll_write_active_ = false;
        read_slice_active_ = false;
    }

    void end_position_phase() {
        position_phase_ = false;
        poll_write_active_ = false;
        read_slice_active_ = false;
    }

    bool begin_poll_write(size_t expected_bytes) {
        poll_write_active_ = false;
        poll_write_failed_ = true;
        poll_write_expected_ = expected_bytes;
        poll_write_accepted_ = 0;
        if (!position_phase_ || expected_bytes == 0u) return false;
        const int available = stream_.availableForWrite();
        if (available < 0 || (size_t)available < expected_bytes) return false;
        poll_write_failed_ = false;
        poll_write_active_ = true;
        return true;
    }

    bool finish_poll_write() {
        const bool complete = poll_write_active_ && !poll_write_failed_ &&
            poll_write_accepted_ == poll_write_expected_;
        poll_write_active_ = false;
        return complete;
    }

    void begin_read_slice(uint32_t max_ms, size_t max_bytes) {
        read_slice_started_ = (uint32_t)millis();
        read_slice_max_ms_ = max_ms;
        read_slice_max_bytes_ = max_bytes;
        read_slice_bytes_ = 0;
        read_slice_active_ = position_phase_ && max_ms > 0u && max_bytes > 0u;
    }

    void finish_read_slice() { read_slice_active_ = false; }

    int available() override {
        if (latched_) return 1;
        if (!position_phase_) return stream_.available();
        if (!read_slice_active_ || read_slice_bytes_ >= read_slice_max_bytes_ ||
            (uint32_t)((uint32_t)millis() - read_slice_started_) >= read_slice_max_ms_) {
            return 0;
        }
        if (stream_.available() <= 0) return 0;
        const int value = stream_.read();
        if (value < 0) return 0;
        latched_byte_ = (uint8_t)value;
        latched_ = true;
        return 1;
    }

    int read() override {
        if (latched_) {
            latched_ = false;
            if (read_slice_active_) ++read_slice_bytes_;
            return latched_byte_;
        }
        if (position_phase_) return -1;
        return stream_.read();
    }

    int peek() override {
        if (latched_) return latched_byte_;
        if (position_phase_) return -1;
        return stream_.peek();
    }

    void flush() override { stream_.flush(); }

    int availableForWrite() override { return stream_.availableForWrite(); }

    size_t write(uint8_t value) override { return write(&value, 1u); }

    size_t write(const uint8_t* data, size_t size) override {
        if (!position_phase_) return stream_.write(data, size);
        if (!poll_write_active_ || poll_write_failed_ || size == 0u ||
            poll_write_accepted_ + size > poll_write_expected_) {
            if (size != 0u) poll_write_failed_ = true;
            return 0u;
        }
        const size_t accepted = stream_.write(data, size);
        poll_write_accepted_ += accepted;
        if (accepted != size) poll_write_failed_ = true;
        return accepted;
    }

private:
    Stream& stream_;
    bool position_phase_ = false;
    bool poll_write_active_ = false;
    bool poll_write_failed_ = false;
    bool read_slice_active_ = false;
    bool latched_ = false;
    uint8_t latched_byte_ = 0;
    size_t poll_write_expected_ = 0;
    size_t poll_write_accepted_ = 0;
    uint32_t read_slice_started_ = 0;
    uint32_t read_slice_max_ms_ = 0;
    size_t read_slice_max_bytes_ = 0;
    size_t read_slice_bytes_ = 0;
};
