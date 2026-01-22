import Link from 'next/link';

export default function Home() {
    return (
        <div>
            <h1>Stratolink</h1>
            <p>Pico-Balloon Telemetry System</p>
            <Link href="/dashboard">View Dashboard</Link>
        </div>
    );
}
