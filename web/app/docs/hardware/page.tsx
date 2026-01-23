import Link from 'next/link';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';

export default function HardwarePage() {
    return (
        <div className="min-h-screen bg-background">
            <Navigation />
            <main>
                <div className="border-b bg-background">
                    <div className="mx-auto max-w-4xl px-6 py-16 sm:px-8 sm:py-24">
                        <Link
                            href="/docs"
                            className="mb-8 inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
                        >
                            <svg className="mr-2 w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                            </svg>
                            Back to Documentation
                        </Link>
                        <h1 className="text-4xl font-light tracking-tight text-foreground sm:text-5xl">
                            Hardware Setup
                        </h1>
                        <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
                            Configure your RAK3172 hardware and flash the Stratolink firmware.
                        </p>
                    </div>
                </div>

                <div className="mx-auto max-w-4xl px-6 py-16 sm:px-8 sm:py-24">
                    <div className="prose prose-slate max-w-none dark:prose-invert">
                        <h2>Hardware Requirements</h2>
                        <ul>
                            <li>RAK3172-SIP development board or compatible LoRaWAN module</li>
                            <li>GNSS antenna (for GPS positioning)</li>
                            <li>LoRa antenna (for LoRaWAN communication)</li>
                            <li>USB cable for programming and power</li>
                            <li>Optional: External battery pack for field deployment</li>
                        </ul>

                        <h2>Installation</h2>
                        <h3>1. Install PlatformIO</h3>
                        <p>
                            PlatformIO is required to build and flash the firmware. You can install it as:
                        </p>
                        <ul>
                            <li><strong>VS Code Extension</strong> - Recommended for beginners</li>
                            <li><strong>CLI Tool</strong> - For command-line usage</li>
                            <li><strong>Standalone IDE</strong> - Full-featured development environment</li>
                        </ul>
                        <p>
                            Download from <a href="https://platformio.org" target="_blank" rel="noopener noreferrer">platformio.org</a>
                        </p>

                        <h3>2. Clone Repository</h3>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>git clone https://github.com/ShepherdKruse/Stratolink.git
cd Stratolink</code>
                        </pre>

                        <h3>3. Configure LoRaWAN Credentials</h3>
                        <p>
                            You'll need credentials from The Things Network:
                        </p>
                        <ol>
                            <li>Create an account at <a href="https://console.thethingsnetwork.org" target="_blank" rel="noopener noreferrer">The Things Network</a></li>
                            <li>Create a new application</li>
                            <li>Register your device and obtain:
                                <ul>
                                    <li><strong>DEV_EUI</strong> - Device EUI (unique identifier)</li>
                                    <li><strong>APP_EUI</strong> - Application EUI</li>
                                    <li><strong>APP_KEY</strong> - Application key (keep this secret)</li>
                                </ul>
                            </li>
                        </ol>

                        <h3>4. Set Up Secrets File</h3>
                        <p>
                            The firmware uses a gitignored secrets file to store sensitive credentials:
                        </p>
                        <ol>
                            <li>Copy <code>firmware/include/config.h</code> to <code>firmware/include/secrets.h</code></li>
                            <li>Edit <code>secrets.h</code> and replace placeholder values:
                                <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                                    <code>{`#define LORAWAN_DEV_EUI "YOUR_DEV_EUI_HERE"
#define LORAWAN_APP_EUI "YOUR_APP_EUI_HERE"
#define LORAWAN_APP_KEY "YOUR_APP_KEY_HERE"`}</code>
                                </pre>
                            </li>
                            <li><strong>Important:</strong> Never commit <code>secrets.h</code> to version control</li>
                        </ol>

                        <h3>5. Configure Region</h3>
                        <p>
                            Set your LoRaWAN region in <code>config.h</code>:
                        </p>
                        <ul>
                            <li>US915 - United States</li>
                            <li>EU868 - Europe</li>
                            <li>AS923 - Asia</li>
                            <li>AU915 - Australia</li>
                        </ul>

                        <h2>Building and Flashing</h2>
                        <h3>Build Firmware</h3>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>cd firmware
pio run</code>
                        </pre>

                        <h3>Flash to Device</h3>
                        <p>
                            Connect your RAK3172 via USB and flash the firmware:
                        </p>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>pio run --target upload</code>
                        </pre>
                        <p>
                            Or use the provided script:
                        </p>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>./flash_firmware.bat</code>
                        </pre>

                        <h3>Monitor Serial Output</h3>
                        <p>
                            View debug messages and telemetry:
                        </p>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>pio device monitor</code>
                        </pre>

                        <h2>PCB and Circuit Design</h2>
                        <p>
                            For custom PCB designs and circuit schematics, see the{' '}
                            <a href="https://github.com/ShepherdKruse/Stratolink/tree/main/hardware" target="_blank" rel="noopener noreferrer">
                                hardware directory
                            </a>{' '}
                            in the repository. Files are provided in KiCad format.
                        </p>

                        <h2>Troubleshooting</h2>
                        <h3>Device Not Detected</h3>
                        <ul>
                            <li>Check USB cable connection</li>
                            <li>Install USB drivers if needed (check RAK documentation)</li>
                            <li>Try a different USB port</li>
                        </ul>

                        <h3>Build Errors</h3>
                        <ul>
                            <li>Ensure PlatformIO is up to date: <code>pio upgrade</code></li>
                            <li>Check that all required libraries are installed</li>
                            <li>Verify <code>platformio.ini</code> configuration</li>
                        </ul>

                        <h3>LoRaWAN Connection Issues</h3>
                        <ul>
                            <li>Verify credentials in <code>secrets.h</code></li>
                            <li>Check that your region matches TTN configuration</li>
                            <li>Ensure antennas are properly connected</li>
                            <li>Check TTN console for device registration status</li>
                        </ul>

                        <div className="mt-12 rounded-sm border border-border bg-card p-6">
                            <h3 className="mt-0">Next Steps</h3>
                            <p>
                                Once your hardware is configured, continue with the{' '}
                                <Link href="/docs/getting-started">Getting Started guide</Link> to set up the web application.
                            </p>
                        </div>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}
