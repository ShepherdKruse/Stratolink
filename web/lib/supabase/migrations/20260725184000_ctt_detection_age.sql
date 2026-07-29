-- fPort-11 wire v2 replaces the locally meaningful listen-window number with
-- saturating queue age. This preserves the actual wildlife-detection time
-- when the shared auxiliary uplink budget delays delivery for hours or days.
ALTER TABLE public.wildlife_detections
    ALTER COLUMN listen_window DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS event_version smallint
        CHECK (event_version IN (1, 2)),
    ADD COLUMN IF NOT EXISTS detection_age_min integer
        CHECK (detection_age_min BETWEEN 0 AND 65535),
    ADD COLUMN IF NOT EXISTS detected_at timestamptz;

-- Rows written before wire v2 are unambiguously v1 because the original
-- schema required listen_window and had no age/time columns. Backfill them so
-- future inserts cannot bypass the version-specific consistency constraint
-- with a NULL version.
UPDATE public.wildlife_detections
    SET event_version = 1
    WHERE event_version IS NULL;
ALTER TABLE public.wildlife_detections
    ALTER COLUMN event_version SET NOT NULL;

ALTER TABLE public.wildlife_detections
    DROP CONSTRAINT IF EXISTS wildlife_detections_version_fields_check;
ALTER TABLE public.wildlife_detections
    ADD CONSTRAINT wildlife_detections_version_fields_check CHECK (
        (event_version = 1 AND listen_window IS NOT NULL AND
         detection_age_min IS NULL AND detected_at IS NULL) OR
        (event_version = 2 AND listen_window IS NULL AND
         detection_age_min IS NOT NULL AND detected_at IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS idx_wildlife_detections_detected_time
    ON public.wildlife_detections (device_id, detected_at DESC)
    WHERE detected_at IS NOT NULL;

COMMENT ON COLUMN public.wildlife_detections.detection_age_min IS
    'Whole minutes from first RF detection to fPort-11 encoding, saturated at 65535';
COMMENT ON COLUMN public.wildlife_detections.detected_at IS
    'TTN server receive time minus firmware-reported detection age';
