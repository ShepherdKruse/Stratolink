#include "devnonce_store.h"

#include <stddef.h>

#define DEVNONCE_RECORD_TAG 0x534C0000u /* "SL" + uint16 nonce */

uint64_t devnonce_record_encode(uint16_t nonce) {
    uint32_t value = DEVNONCE_RECORD_TAG | nonce;
    return ((uint64_t)(~value) << 32) | value;
}

bool devnonce_record_decode(uint64_t record, uint16_t* nonce) {
    uint32_t value = (uint32_t)record;
    uint32_t check = (uint32_t)(record >> 32);
    if ((value & 0xFFFF0000u) != DEVNONCE_RECORD_TAG || check != ~value) {
        return false;
    }
    if (nonce) *nonce = (uint16_t)value;
    return true;
}

bool devnonce_value_next(bool have_previous, uint16_t previous, uint16_t* next) {
    if (!next || (have_previous && previous == UINT16_MAX)) return false;
    *next = have_previous ? (uint16_t)(previous + 1u) : 0u;
    return true;
}

#if defined(ARDUINO_ARCH_STM32)
#include <Arduino.h>

/* The board definition caps the linker's flash region at 252 KiB, reserving
 * physical pages 126 and 127 exclusively for this journal. STM32WLE5CC has
 * 128 x 2 KiB pages and programs one aligned 64-bit doubleword at a time. */
static constexpr uint32_t PAGE_BYTES = 0x800u;
static constexpr uint32_t PAGE0_ADDR = 0x0803F000u;
static constexpr uint32_t PAGE1_ADDR = 0x0803F800u;
static constexpr uint32_t RECORD_BYTES = 8u;
static constexpr uint16_t RECORDS_PER_PAGE = PAGE_BYTES / RECORD_BYTES;

struct page_scan_t {
    bool have_valid;
    uint16_t max_nonce;
    int16_t first_blank;
};

static uint64_t flash_record(uint32_t page, uint16_t slot) {
    return *(const volatile uint64_t*)(page + (uint32_t)slot * RECORD_BYTES);
}

static page_scan_t scan_page(uint32_t page) {
    page_scan_t scan = {false, 0, -1};
    for (uint16_t slot = 0; slot < RECORDS_PER_PAGE; ++slot) {
        uint64_t record = flash_record(page, slot);
        if (record == UINT64_MAX) {
            if (scan.first_blank < 0) scan.first_blank = (int16_t)slot;
            continue;
        }
        uint16_t nonce = 0;
        if (devnonce_record_decode(record, &nonce) &&
            (!scan.have_valid || nonce > scan.max_nonce)) {
            scan.have_valid = true;
            scan.max_nonce = nonce;
        }
        /* A torn/invalid record is deliberately skipped. A later blank slot
         * can safely carry the retry while the valid record on the other page
         * remains the recovery anchor. */
    }
    return scan;
}

static bool erase_page(uint32_t address) {
    FLASH_EraseInitTypeDef erase = {};
    erase.TypeErase = FLASH_TYPEERASE_PAGES;
    erase.Page = (address - FLASH_BASE) / PAGE_BYTES;
    erase.NbPages = 1;
    uint32_t page_error = 0;
    if (HAL_FLASH_Unlock() != HAL_OK) return false;
    __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_ALL_ERRORS);
    bool ok = HAL_FLASHEx_Erase(&erase, &page_error) == HAL_OK;
    (void)HAL_FLASH_Lock();
    return ok;
}

static bool program_record(uint32_t page, uint16_t slot, uint16_t nonce) {
    uint32_t address = page + (uint32_t)slot * RECORD_BYTES;
    uint64_t record = devnonce_record_encode(nonce);
    if (HAL_FLASH_Unlock() != HAL_OK) return false;
    __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_ALL_ERRORS);
    bool ok = HAL_FLASH_Program(FLASH_TYPEPROGRAM_DOUBLEWORD, address, record)
              == HAL_OK;
    (void)HAL_FLASH_Lock();
    return ok && flash_record(page, slot) == record;
}

bool devnonce_next(uint16_t* out) {
    if (!out) return false;
    page_scan_t p0 = scan_page(PAGE0_ADDR);
    page_scan_t p1 = scan_page(PAGE1_ADDR);

    bool have = p0.have_valid || p1.have_valid;
    uint16_t previous = 0;
    uint32_t active_page = PAGE0_ADDR;
    page_scan_t* active = &p0;
    uint32_t other_page = PAGE1_ADDR;
    page_scan_t* other = &p1;

    if (p1.have_valid && (!p0.have_valid || p1.max_nonce > p0.max_nonce)) {
        previous = p1.max_nonce;
        active_page = PAGE1_ADDR; active = &p1;
        other_page = PAGE0_ADDR; other = &p0;
    } else if (p0.have_valid) {
        previous = p0.max_nonce;
    }

    uint16_t next = 0;
    if (!devnonce_value_next(have, previous, &next)) return false;

    if (active->first_blank < 0) {
        /* The page containing the newest valid value remains untouched until
         * the other page is erased and the successor is durably verified. */
        if (!erase_page(other_page)) return false;
        *other = scan_page(other_page);
        if (other->first_blank < 0) return false;
        active_page = other_page;
        active = other;
    }

    if (!program_record(active_page, (uint16_t)active->first_blank, next)) {
        return false;
    }
    *out = next;
    return true;
}

#else

bool devnonce_next(uint16_t* out) {
    (void)out;
    return false;
}

#endif
