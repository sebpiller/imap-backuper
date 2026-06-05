package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.util.Durations;
import lombok.extern.slf4j.Slf4j;

import java.time.Duration;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

/**
 * Logs download progress (messages processed, percent complete, ETA) on a fixed
 * schedule until {@link #close()} is called.
 */
@Slf4j
public final class ProgressReporter implements AutoCloseable {

    private final DownloadStatistics statistics;
    private final long startNanos;
    private final ScheduledExecutorService scheduler;
    private final ScheduledFuture<?> task;

    private ProgressReporter(DownloadStatistics statistics, long startNanos, long periodSeconds) {
        this.statistics = statistics;
        this.startNanos = startNanos;
        this.scheduler = Executors.newScheduledThreadPool(1);
        this.task = scheduler.scheduleAtFixedRate(this::reportProgress, periodSeconds, periodSeconds, TimeUnit.SECONDS);
    }

    /** Starts a reporter that logs every {@code periodSeconds} seconds. */
    public static ProgressReporter start(DownloadStatistics statistics, long startNanos, long periodSeconds) {
        return new ProgressReporter(statistics, startNanos, periodSeconds);
    }

    /**
     * Reports progress: messages processed, % complete, and ETA.
     */
    private void reportProgress() {
        var processed = statistics.mailsSaved();
        var total = statistics.totalMessagesToProcess();

        var percentDone = total == 0 ? 0 : 100.0 * processed / total;
        var elapsedNanos = System.nanoTime() - startNanos;
        var elapsedMs = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

        long remaining = total - processed;
        long etaMs;
        if (processed == 0) {
            etaMs = 0;
        } else {
            var msPerMessage = (double) elapsedMs / processed;
            etaMs = (long) (remaining * msPerMessage);
        }

        log.info("Progress: {} / {} messages ({}%) | Elapsed: {} | ETA: {}",
                processed, total, percentDone,
                Durations.format(Duration.ofMillis(elapsedMs)),
                Durations.format(Duration.ofMillis(etaMs))
        );
    }

    @Override
    public void close() {
        task.cancel(false);
        scheduler.shutdown();
    }
}
