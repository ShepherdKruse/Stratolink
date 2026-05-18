'use client';

import { useEffect, useRef } from 'react';
import { initMissionOutreach } from './missionOutreachEffects';

interface MissionOutreachClientProps {
    html: string;
}

export default function MissionOutreachClient({ html }: MissionOutreachClientProps) {
    const rootRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const root = rootRef.current;
        if (!root) return;
        return initMissionOutreach(root);
    }, [html]);

    return (
        <div
            ref={rootRef}
            className="mission-outreach"
            dangerouslySetInnerHTML={{ __html: html }}
        />
    );
}
