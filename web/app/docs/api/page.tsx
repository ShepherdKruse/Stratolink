import Link from 'next/link';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';

export default function APIPage() {
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
                            API Reference
                        </h1>
                        <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
                            Integrate with Stratolink using webhooks and API endpoints.
                        </p>
                    </div>
                </div>

                <div className="mx-auto max-w-4xl px-6 py-16 sm:px-8 sm:py-24">
                    <div className="prose prose-slate max-w-none dark:prose-invert">
                        <h2>Overview</h2>
                        <p>
                            Stratolink uses webhooks to receive telemetry data from The Things Network (TTN).
                            The system processes incoming data and stores it in Supabase for real-time dashboard visualization.
                        </p>

                        <h2>TTN Webhook Integration</h2>
                        <h3>Endpoint</h3>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>POST https://your-domain.com/api/ttn-webhook</code>
                        </pre>

                        <h3>Configuration</h3>
                        <p>
                            Configure the webhook in The Things Network Console:
                        </p>
                        <ol>
                            <li>Navigate to Applications → Your Application → Integrations → Webhooks</li>
                            <li>Add a new webhook with format: <strong>JSON</strong></li>
                            <li>Set the webhook URL to your deployed endpoint</li>
                            <li>Save the configuration</li>
                        </ol>

                        <h3>Webhook Payload</h3>
                        <p>
                            The webhook receives JSON payloads from TTN with the following structure:
                        </p>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>{`{
  "end_device_ids": {
    "device_id": "balloon-001",
    "dev_eui": "...",
    "application_ids": {
      "application_id": "..."
    }
  },
  "received_at": "2024-01-01T12:00:00Z",
  "uplink_message": {
    "frm_payload": "base64_encoded_payload",
    "decoded_payload": {
      "lat": 40.7128,
      "lon": -74.0060,
      "altitude_m": 30000,
      "battery_voltage": 3.72,
      "temperature": -45.2,
      "pressure": 120.5
    },
    "rx_metadata": [{
      "rssi": -112,
      "snr": 8.5
    }]
  }
}`}</code>
                        </pre>

                        <h3>Payload Decoding</h3>
                        <p>
                            The webhook handler automatically decodes base64-encoded payloads. Ensure your firmware
                            encodes telemetry data in a format compatible with the decoder in{' '}
                            <code>web/app/api/ttn-webhook/route.ts</code>.
                        </p>

                        <h2>Data Storage</h2>
                        <p>
                            Telemetry data is stored in Supabase with the following schema:
                        </p>
                        <h3>Telemetry Table</h3>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>{`CREATE TABLE telemetry (
  id BIGSERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
  time TIMESTAMPTZ NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  altitude_m DOUBLE PRECISION,
  battery_voltage DOUBLE PRECISION,
  temperature DOUBLE PRECISION,
  pressure DOUBLE PRECISION,
  rssi DOUBLE PRECISION,
  velocity_x DOUBLE PRECISION,
  velocity_y DOUBLE PRECISION,
  raw_payload JSONB,
  location GEOGRAPHY(POINT, 4326)
);`}</code>
                        </pre>

                        <h2>Querying Data</h2>
                        <p>
                            Access telemetry data directly from Supabase using SQL or the Supabase client libraries.
                        </p>

                        <h3>Example: Get Latest Telemetry</h3>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>{`SELECT * FROM telemetry
WHERE device_id = 'balloon-001'
ORDER BY time DESC
LIMIT 1;`}</code>
                        </pre>

                        <h3>Example: Get Flight Path</h3>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>{`SELECT lat, lon, time, altitude_m
FROM telemetry
WHERE device_id = 'balloon-001'
  AND time >= NOW() - INTERVAL '24 hours'
ORDER BY time ASC;`}</code>
                        </pre>

                        <h3>Example: Active Balloons</h3>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>{`SELECT DISTINCT device_id
FROM telemetry
WHERE time >= NOW() - INTERVAL '2 hours'
  AND altitude_m > 100;`}</code>
                        </pre>

                        <h2>Supabase Client Integration</h2>
                        <p>
                            Use the Supabase JavaScript client to query data programmatically:
                        </p>
                        <pre className="bg-muted p-4 rounded-sm overflow-x-auto">
                            <code>{`import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

// Query latest telemetry
const { data, error } = await supabase
  .from('telemetry')
  .select('*')
  .eq('device_id', 'balloon-001')
  .order('time', { ascending: false })
  .limit(1);`}</code>
                        </pre>

                        <h2>Security</h2>
                        <ul>
                            <li>Webhook endpoints should validate incoming requests</li>
                            <li>Use Supabase Row Level Security (RLS) policies to control data access</li>
                            <li>Never expose service role keys in client-side code</li>
                            <li>Validate and sanitize all incoming telemetry data</li>
                        </ul>

                        <h2>Rate Limiting</h2>
                        <p>
                            Consider implementing rate limiting for webhook endpoints to prevent abuse.
                            Vercel provides built-in rate limiting for API routes.
                        </p>

                        <div className="mt-12 rounded-sm border border-border bg-card p-6">
                            <h3 className="mt-0">Need Help?</h3>
                            <p>
                                For integration support, check the{' '}
                                <Link href="/docs/troubleshooting">troubleshooting guide</Link> or{' '}
                                <Link href="/#contact">contact us</Link>.
                            </p>
                        </div>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}
