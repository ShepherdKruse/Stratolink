import Link from 'next/link';
import Image from 'next/image';

export default function Home() {
    return (
        <div style={{ textAlign: 'center', padding: '2rem' }}>
            <Image
                src="/images/logo.png"
                alt="Stratolink Logo"
                width={300}
                height={300}
                priority
            />
            <h1>Stratolink</h1>
            <p>Global Pico-Connectivity</p>
            <p>Pico-Balloon Telemetry System</p>
            <Link href="/dashboard">View Dashboard</Link>
        </div>
    );
}
