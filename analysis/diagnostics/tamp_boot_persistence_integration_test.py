#!/usr/bin/env python3
"""Source gate for the physical STM32WLE5 TAMP layout and boot record."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/src/power_manager.cpp"
MAIN = ROOT / "firmware/src/main.cpp"


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    unlock = text[text.index("static void enable_backup_access"):
                  text.index("static bool invalidate_session_and_lease_markers")]
    record = text[text.index("uint32_t power_manager_record_boot"):
                  text.index("bool power_manager_load_b2b_msg_id")]

    assert "READ_BIT(PWR->CR1, PWR_CR1_DBP)" in unlock
    assert "__DSB();" in unlock
    assert "#define STRATO_TAMP_WORD_COUNT  20" in text
    assert "#define STRATO_BOOT_WORD        19" in text
    assert "STRATO_BOOT_WORD == STRATO_TAMP_WORD_COUNT - 1" in text
    assert "tamp_boot_record_decode(*boot_word, &previous)" in record
    assert "uint32_t record = tamp_boot_record_encode(next);" in record
    assert "*boot_word == record" in record
    assert "tamp_boot_record_decode(*boot_word, &observed)" in record
    assert "*boot_word = 0;\n    return 0;" in record
    assert "BKP30" not in text and "BKP31" not in text
    setup = main[main.index("void setup()") : main.index("void loop()")]
    assert setup.index("power_manager_init();") < setup.index(
        "boot_count = power_manager_record_boot();"
    )
    assert setup.index("power_manager_init();") < setup.index("command_init();")
    print("PASS: STM32WLE5 20-word TAMP layout and packed boot record")


if __name__ == "__main__":
    main()
