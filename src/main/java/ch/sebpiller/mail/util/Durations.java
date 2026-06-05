package ch.sebpiller.mail.util;

import java.time.Duration;

/**
 * Formats {@link Duration} values for human-readable logging.
 */
public final class Durations {

    private Durations() {
    }

    /**
     * Formats a duration as a human-readable {@code HH:mm:ss.SSS} string.
     */
    public static String format(Duration duration) {
        var millis = duration.toMillis();
        return String.format("%02d:%02d:%02d.%03d",
                millis / 3_600_000,
                (millis / 60_000) % 60,
                (millis / 1_000) % 60,
                millis % 1_000);
    }
}
