@echo off
echo Flashing Stratolink firmware to RAK3172...

pio run --target upload

if %errorlevel% neq 0 (
    echo Error: Firmware upload failed.
    exit /b 1
)

echo Firmware uploaded successfully.
