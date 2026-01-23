'use client';

import { useState, useEffect } from 'react';

export function useIsMobile() {
    const [isMobile, setIsMobile] = useState(false);

    useEffect(() => {
        const mediaQuery = window.matchMedia('(max-width: 768px)');
        
        // Set initial value
        setIsMobile(mediaQuery.matches);

        // Create handler
        const handleChange = (event: MediaQueryListEvent | MediaQueryList) => {
            setIsMobile(event.matches);
        };

        // Add listener
        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', handleChange);
        } else {
            // Fallback for older browsers
            mediaQuery.addListener(handleChange);
        }

        // Cleanup
        return () => {
            if (mediaQuery.removeEventListener) {
                mediaQuery.removeEventListener('change', handleChange);
            } else {
                mediaQuery.removeListener(handleChange);
            }
        };
    }, []);

    return isMobile;
}
