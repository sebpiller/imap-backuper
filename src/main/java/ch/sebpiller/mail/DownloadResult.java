package ch.sebpiller.mail;

import ch.sebpiller.mail.util.Durations;
import lombok.extern.slf4j.Slf4j;

import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Immutable summary of a finished {@link MailDownloader#run()}: how many mails
 * and attachments were saved, how long it took, the per-sender monthly tally and
 * the per-domain on-disk statistics.
 */
public record DownloadResult(int mailsSaved,
                             int attachmentsSaved,
                             int messagesSkipped,
                             Duration elapsed,
                             Map<String, Map<String, Integer>> senderMonthCounts,
                             List<DomainStatistic> domainStatistics) {

    /** Aggregated counts and on-disk size for a single sender domain. */
    public record DomainStatistic(String domain, long emailCount, long totalSizeBytes) {
    }

    /**
     * Logs the full summary (counts, sender stats, domain stats) the same way the
     * original collector did, for callers that just want a human-readable report.
     */
    public void logSummary() {
        Logging.log(this);
    }

    @Slf4j
    private static final class Logging {
        private static void log(DownloadResult result) {
            log.info("===== Full mail download summary =====");
            log.info("Mails saved       : {}", result.mailsSaved());
            log.info("Attachments saved : {}", result.attachmentsSaved());
            log.info("Messages skipped  : {}", result.messagesSkipped());
            log.info("Processing time   : {} ms ({})",
                    result.elapsed().toMillis(), Durations.format(result.elapsed()));
            log.info("======================================");

            log.info("===== Sender email count by month =====");
            if (result.senderMonthCounts().isEmpty()) {
                log.info("No senders found");
            } else {
                result.senderMonthCounts().forEach((sender, months) -> {
                    log.info("Sender: {}", sender);
                    months.forEach((month, count) -> log.info("  {}: {} email(s)", month, count));
                });
            }
            log.info("======================================");

            log.info("===== Domain statistics =====");
            for (var stat : result.domainStatistics()) {
                var sizeInKB = stat.totalSizeBytes() / 1024.0;
                var sizeInMB = sizeInKB / 1024.0;
                var sizeFormatted = sizeInMB >= 1.0
                        ? String.format("%.2f MB", sizeInMB)
                        : String.format("%.2f KB", sizeInKB);
                log.info("Domain: {} | Emails: {} | Total size: {} ({} bytes)",
                        stat.domain(), stat.emailCount(), sizeFormatted, stat.totalSizeBytes());
            }
            log.info("============================");
        }
    }
}
