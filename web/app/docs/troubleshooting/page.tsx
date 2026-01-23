import Link from 'next/link';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';

export default function TroubleshootingPage() {
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
                            Troubleshooting
                        </h1>
                        <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
                            Common issues and solutions for Stratolink setup and operation.
                        </p>
                    </div>
                </div>

                <div className="mx-auto max-w-4xl px-6 py-16 sm:px-8 sm:py-24">
                    <div className="docs-content">
                        <h2>Hardware Issues</h2>
                        
                        <h3>Device Not Detected by PlatformIO</h3>
                        <ul>
                            <li>Check USB cable connection and try a different cable</li>
                            <li>Install USB drivers from RAK documentation</li>
                            <li>Try a different USB port (prefer USB 2.0 ports)</li>
                            <li>On Windows, check Device Manager for COM port assignment</li>
                            <li>On Linux, ensure user has permissions for USB devices</li>
                        </ul>

                        <h3>Firmware Won't Build</h3>
                        <ul>
                            <li>Update PlatformIO: <code className="text-sm">pio upgrade</code></li>
                            <li>Check <code className="text-sm">platformio.ini</code> for correct board configuration</li>
                            <li>Verify all required libraries are installed</li>
                            <li>Clear build cache: <code className="text-sm">pio run --target clean</code></li>
                        </ul>

                        <h3>LoRaWAN Connection Fails</h3>
                        <ul>
                            <li>Verify credentials in <code className="text-sm">secrets.h</code> match TTN console</li>
                            <li>Check that region setting matches your TTN application region</li>
                            <li>Ensure antennas are properly connected</li>
                            <li>Check TTN console for device activation status</li>
                            <li>Monitor serial output for error messages</li>
                        </ul>

                        <h3>GPS Not Acquiring Fix</h3>
                        <ul>
                            <li>Ensure GPS antenna has clear view of sky</li>
                            <li>Wait several minutes for cold start (first fix can take 5-10 minutes)</li>
                            <li>Check antenna connection</li>
                            <li>Verify GNSS library configuration in firmware</li>
                        </ul>

                        <h2>Web Application Issues</h2>

                        <h3>Build Errors</h3>
                        <ul>
                            <li>Clear <code className="text-sm">.next</code> directory and rebuild</li>
                            <li>Delete <code className="text-sm">node_modules</code> and reinstall: <code className="text-sm">npm install</code></li>
                            <li>Check Node.js version (requires 18+)</li>
                            <li>Verify all environment variables are set in <code className="text-sm">.env.local</code></li>
                        </ul>

                        <h3>Supabase Connection Issues</h3>
                        <ul>
                            <li>Verify <code className="text-sm">NEXT_PUBLIC_SUPABASE_URL</code> and <code className="text-sm">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> are correct</li>
                            <li>Check Supabase project status in dashboard</li>
                            <li>Ensure PostGIS extension is enabled</li>
                            <li>Verify database schema has been applied</li>
                            <li>Check Supabase logs for connection errors</li>
                        </ul>

                        <h3>Map Not Displaying</h3>
                        <ul>
                            <li>Verify <code className="text-sm">NEXT_PUBLIC_MAPBOX_TOKEN</code> is set</li>
                            <li>Check Mapbox token permissions and usage limits</li>
                            <li>Ensure token has access to required styles</li>
                            <li>Check browser console for Mapbox API errors</li>
                        </ul>

                        <h3>No Balloons Showing on Dashboard</h3>
                        <ul>
                            <li>Verify webhook is configured in TTN console</li>
                            <li>Check webhook URL matches your deployed domain</li>
                            <li>Verify webhook format is set to JSON</li>
                            <li>Check Vercel function logs for webhook errors</li>
                            <li>Ensure telemetry data exists in Supabase</li>
                            <li>Check time filters - dashboard shows balloons from last 24 hours</li>
                        </ul>

                        <h2>Webhook Issues</h2>

                        <h3>Webhook Not Receiving Data</h3>
                        <ul>
                            <li>Verify webhook URL is accessible (test with curl or Postman)</li>
                            <li>Check TTN console for webhook delivery status</li>
                            <li>Review Vercel function logs for incoming requests</li>
                            <li>Ensure webhook format matches expected JSON structure</li>
                            <li>Check for CORS or authentication issues</li>
                        </ul>

                        <h3>Data Not Appearing in Database</h3>
                        <ul>
                            <li>Check webhook route logs for errors</li>
                            <li>Verify payload decoding logic matches firmware encoding</li>
                            <li>Check Supabase table permissions and RLS policies</li>
                            <li>Verify database schema includes all required columns</li>
                            <li>Test direct database insert to isolate webhook issues</li>
                        </ul>

                        <h2>Dashboard Issues</h2>

                        <h3>Performance Problems</h3>
                        <ul>
                            <li>Switch to 2D map view for better performance</li>
                            <li>Reduce number of balloons displayed (adjust time filter)</li>
                            <li>Check browser console for JavaScript errors</li>
                            <li>Clear browser cache and reload</li>
                            <li>Disable browser extensions that might interfere</li>
                        </ul>

                        <h3>Timeline Not Working</h3>
                        <ul>
                            <li>Ensure flight path data exists for selected balloon</li>
                            <li>Check that telemetry data has valid timestamps</li>
                            <li>Verify timeline component is receiving correct props</li>
                            <li>Check browser console for errors</li>
                        </ul>

                        <h2>Deployment Issues</h2>

                        <h3>Vercel Build Fails</h3>
                        <ul>
                            <li>Check build logs for specific error messages</li>
                            <li>Verify all environment variables are set in Vercel dashboard</li>
                            <li>Ensure <code className="text-sm">package.json</code> has correct build scripts</li>
                            <li>Check for TypeScript or linting errors locally first</li>
                            <li>Verify Node.js version in Vercel matches local version</li>
                        </ul>

                        <h3>Environment Variables Not Working</h3>
                        <ul>
                            <li>Ensure variables are prefixed with <code className="text-sm">NEXT_PUBLIC_</code> for client-side access</li>
                            <li>Redeploy after adding new environment variables</li>
                            <li>Check Vercel dashboard for variable typos</li>
                            <li>Verify variables are not in <code className="text-sm">.gitignore</code> (they shouldn't be committed, but should be in Vercel)</li>
                        </ul>

                        <h2>General Debugging Tips</h2>
                        <ul>
                            <li><strong>Check Logs:</strong> Review serial output, browser console, and Vercel function logs</li>
                            <li><strong>Test Incrementally:</strong> Verify each component works independently</li>
                            <li><strong>Use Test Data:</strong> Insert test records directly into Supabase to verify dashboard functionality</li>
                            <li><strong>Network Tools:</strong> Use browser DevTools Network tab to inspect API calls</li>
                            <li><strong>Version Check:</strong> Ensure all dependencies are up to date</li>
                        </ul>

                        <div className="mt-12 rounded-sm border border-border bg-card p-6">
                            <h3 className="mt-0">Still Need Help?</h3>
                            <p>
                                If you've tried these solutions and still encounter issues,{' '}
                                <Link href="/#contact">contact our support team</Link> with:
                            </p>
                            <ul>
                                <li>Description of the problem</li>
                                <li>Steps to reproduce</li>
                                <li>Error messages or logs</li>
                                <li>Your setup details (hardware, software versions)</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}
