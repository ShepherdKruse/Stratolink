import Link from 'next/link';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';

export default function GettingStartedPage() {
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
                            Getting Started
                        </h1>
                        <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
                            Set up your Stratolink system from hardware to dashboard in a few simple steps.
                        </p>
                    </div>
                </div>

                <div className="mx-auto max-w-4xl px-6 py-16 sm:px-8 sm:py-24">
                    <div className="prose prose-slate max-w-none dark:prose-invert">
                        <h2>Prerequisites</h2>
                        <ul>
                            <li>RAK3172 development board or compatible LoRaWAN module</li>
                            <li>PlatformIO CLI or PlatformIO IDE</li>
                            <li>Node.js 18 or higher</li>
                            <li>Supabase account (free tier available)</li>
                            <li>The Things Network account (free tier available)</li>
                            <li>Mapbox account (for map visualization)</li>
                        </ul>

                        <h2>Step 1: Hardware Setup</h2>
                        <p>
                            Begin by configuring your RAK3172 hardware. For detailed hardware setup instructions,
                            see the <Link href="/docs/hardware">Hardware Setup guide</Link>.
                        </p>
                        <ol>
                            <li>Connect your RAK3172 to your computer via USB</li>
                            <li>Install PlatformIO if you haven't already</li>
                            <li>Clone the Stratolink repository</li>
                            <li>Navigate to the firmware directory</li>
                        </ol>

                        <h2>Step 2: Configure Firmware</h2>
                        <p>
                            Set up your LoRaWAN credentials in the firmware:
                        </p>
                        <ol>
                            <li>Copy <code>firmware/include/config.h</code> values to <code>firmware/include/secrets.h</code></li>
                            <li>Edit <code>firmware/include/secrets.h</code> with your TTN credentials:
                                <ul>
                                    <li>DEV_EUI</li>
                                    <li>APP_EUI</li>
                                    <li>APP_KEY</li>
                                </ul>
                            </li>
                            <li>Build firmware: <code>pio run</code></li>
                            <li>Upload to device: <code>pio run --target upload</code></li>
                        </ol>

                        <h2>Step 3: Set Up Supabase</h2>
                        <ol>
                            <li>Create a new Supabase project at <a href="https://supabase.com" target="_blank" rel="noopener noreferrer">supabase.com</a></li>
                            <li>Navigate to the SQL Editor</li>
                            <li>Run the schema SQL from <code>web/lib/supabase/schema.sql</code></li>
                            <li>Enable the PostGIS extension if not already enabled</li>
                            <li>Copy your project URL and anon key from Settings → API</li>
                        </ol>

                        <h2>Step 4: Configure Web Application</h2>
                        <ol>
                            <li>Navigate to the <code>web</code> directory</li>
                            <li>Install dependencies: <code>npm install</code></li>
                            <li>Copy <code>.env.local.example</code> to <code>.env.local</code></li>
                            <li>Add your credentials to <code>.env.local</code>:
                                <ul>
                                    <li><code>NEXT_PUBLIC_SUPABASE_URL</code> - Your Supabase project URL</li>
                                    <li><code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> - Your Supabase anon key</li>
                                    <li><code>NEXT_PUBLIC_MAPBOX_TOKEN</code> - Your Mapbox access token</li>
                                </ul>
                            </li>
                            <li>Start the development server: <code>npm run dev</code></li>
                        </ol>

                        <h2>Step 5: Configure TTN Webhook</h2>
                        <ol>
                            <li>Log into <a href="https://console.thethingsnetwork.org" target="_blank" rel="noopener noreferrer">The Things Network Console</a></li>
                            <li>Navigate to Applications → Your Application → Integrations → Webhooks</li>
                            <li>Add a new webhook with format: <strong>JSON</strong></li>
                            <li>Set webhook URL: <code>https://your-vercel-domain.com/api/ttn-webhook</code></li>
                            <li>Save the webhook configuration</li>
                        </ol>

                        <h2>Step 6: Deploy to Vercel</h2>
                        <ol>
                            <li>Push your code to GitHub</li>
                            <li>Import your repository in <a href="https://vercel.com" target="_blank" rel="noopener noreferrer">Vercel</a></li>
                            <li>Add your environment variables in Vercel project settings</li>
                            <li>Deploy</li>
                            <li>Update your TTN webhook URL with your Vercel domain</li>
                        </ol>

                        <h2>Next Steps</h2>
                        <ul>
                            <li>Learn how to use the dashboard in the <Link href="/docs/dashboard">Dashboard Guide</Link></li>
                            <li>Explore the <Link href="/docs/api">API Reference</Link> for integration options</li>
                            <li>Check <Link href="/docs/troubleshooting">Troubleshooting</Link> if you encounter issues</li>
                        </ul>

                        <div className="mt-12 rounded-sm border border-border bg-card p-6">
                            <h3 className="mt-0">Need Help?</h3>
                            <p>
                                If you run into issues during setup, check our{' '}
                                <Link href="/docs/troubleshooting">troubleshooting guide</Link> or{' '}
                                <Link href="/#contact">contact support</Link>.
                            </p>
                        </div>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}
