import Link from 'next/link';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';

export default function DashboardPage() {
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
                            Dashboard User Guide
                        </h1>
                        <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
                            Learn how to navigate and use the Mission Control dashboard to track your balloon fleet.
                        </p>
                    </div>
                </div>

                <div className="mx-auto max-w-4xl px-6 py-16 sm:px-8 sm:py-24">
                    <div className="prose prose-slate max-w-none dark:prose-invert">
                        <h2>Overview</h2>
                        <p>
                            The Mission Control dashboard provides real-time visualization of your balloon fleet with
                            interactive maps, telemetry data, and system diagnostics. The interface adapts automatically
                            to desktop and mobile devices.
                        </p>

                        <h2>Desktop Experience</h2>
                        <h3>Global Map View</h3>
                        <p>
                            The main view displays a 3D globe or 2D map showing all active balloons in your fleet.
                            Each balloon appears as a marker with color coding:
                        </p>
                        <ul>
                            <li><strong>Blue markers</strong> - Active balloons (altitude &gt; 100m)</li>
                            <li><strong>Gray markers</strong> - Landed balloons (altitude ≤ 100m)</li>
                        </ul>

                        <h3>Projection Toggle</h3>
                        <p>
                            Switch between 3D globe and 2D map views using the projection toggle in the left sidebar.
                            The 3D globe provides a spatial perspective, while the 2D map offers traditional navigation.
                        </p>

                        <h3>Ride Along Mode</h3>
                        <p>
                            Click any balloon marker to enter "Ride Along" mode:
                        </p>
                        <ul>
                            <li>Camera automatically flies to the balloon's location</li>
                            <li>Pilot HUD overlay appears with real-time telemetry</li>
                            <li>Flight path visualization shows historical trajectory</li>
                            <li>Timeline scrubber at the bottom controls playback time</li>
                        </ul>

                        <h3>System Internals</h3>
                        <p>
                            Click the "System Internals" button in the Pilot HUD to open the detailed sidebar:
                        </p>
                        <ul>
                            <li><strong>3D PCB Model</strong> - Interactive hardware visualization</li>
                            <li><strong>Telemetry Sparklines</strong> - Historical data graphs for battery, temperature, pressure, and signal strength</li>
                            <li><strong>Health Grid</strong> - Current system status at a glance</li>
                            <li><strong>Mission Log</strong> - System events and telemetry history</li>
                        </ul>

                        <h3>Timeline Scrubber</h3>
                        <p>
                            The timeline at the bottom of the screen allows you to:
                        </p>
                        <ul>
                            <li>Scrub through historical flight data</li>
                            <li>View flight path progression over time</li>
                            <li>See telemetry values at specific timestamps</li>
                        </ul>

                        <h2>Mobile Experience</h2>
                        <p>
                            The mobile interface is optimized for touch interaction with a bottom navigation bar:
                        </p>

                        <h3>Radar Tab</h3>
                        <ul>
                            <li>2D tactical map view (optimized for mobile)</li>
                            <li>Compass button to orient map to your physical direction</li>
                            <li>"Nearest" pill showing closest balloon and distance</li>
                            <li>Tap any balloon marker to view details</li>
                        </ul>

                        <h3>Missions Tab</h3>
                        <ul>
                            <li>List of all your balloons (active and landed)</li>
                            <li>Launch button for new missions</li>
                            <li>Tap any balloon card to view details</li>
                        </ul>

                        <h3>Intel Tab</h3>
                        <ul>
                            <li>Fleet statistics (active, landed, total)</li>
                            <li>Top performers leaderboard</li>
                            <li>Fleet conditions summary</li>
                            <li>System status</li>
                        </ul>

                        <h3>Balloon Details Sheet</h3>
                        <p>
                            When you tap a balloon, a bottom sheet appears with:
                        </p>
                        <ul>
                            <li><strong>Peek View</strong> - Status dot, balloon ID, altitude, and Ping button</li>
                            <li><strong>Expanded View</strong> - Full details including 3D PCB, sparklines, health grid, and flight path timeline</li>
                            <li>Use the expand/collapse button to toggle between views</li>
                        </ul>

                        <h2>Key Features</h2>
                        <h3>Real-Time Updates</h3>
                        <p>
                            The dashboard automatically refreshes every 30 seconds to show the latest telemetry data.
                            Connection status is displayed in the sidebar (Intel tab on mobile).
                        </p>

                        <h3>Flight Path Visualization</h3>
                        <p>
                            When a balloon is selected, its historical flight path is displayed as a glowing trail.
                            The trail updates as you scrub through the timeline, showing the balloon's position at different times.
                        </p>

                        <h3>Telemetry Sparklines</h3>
                        <p>
                            Small line graphs show trends over the last 24 hours for:
                        </p>
                        <ul>
                            <li>Battery voltage</li>
                            <li>Temperature</li>
                            <li>Pressure</li>
                            <li>RF signal strength (RSSI)</li>
                        </ul>

                        <h2>Tips</h2>
                        <ul>
                            <li>Use the timeline scrubber to analyze flight patterns and telemetry changes over time</li>
                            <li>Switch to 2D map view for better performance on slower devices</li>
                            <li>On mobile, use the compass feature to orient the map to your physical location</li>
                            <li>The "Nearest" indicator helps you find balloons close to your location</li>
                        </ul>

                        <div className="mt-12 rounded-sm border border-border bg-card p-6">
                            <h3 className="mt-0">Ready to Explore?</h3>
                            <p>
                                <Link href="/dashboard" className="font-medium text-foreground hover:underline">
                                    Open the Mission Control Dashboard
                                </Link>{' '}
                                to start tracking your fleet.
                            </p>
                        </div>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}
