package ch.sebpiller.mail.internal;

import lombok.extern.slf4j.Slf4j;

import javax.mail.Message;
import java.util.Calendar;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Thread-safe tally of how many messages each sender sent per calendar month
 * (keyed {@code "YYYY-MM"}).
 */
@Slf4j
public final class SenderStatistics {

    // Sender statistics: sender -> (yearMonth -> count)
    private final ConcurrentHashMap<String, ConcurrentHashMap<String, AtomicInteger>> senderMonthCounts =
            new ConcurrentHashMap<>();

    /**
     * Tracks sender email statistics: updates the monthly message count for this sender.
     */
    public void track(Message message, String sender) {
        try {
            var sentDate = message.getSentDate();
            if (sentDate == null) {
                sentDate = new Date();
            }
            var yearMonth = formatYearMonth(sentDate);

            senderMonthCounts
                    .computeIfAbsent(sender, k -> new ConcurrentHashMap<>())
                    .computeIfAbsent(yearMonth, k -> new AtomicInteger())
                    .incrementAndGet();
        } catch (Exception e) {
            log.debug("Could not track sender month for {}: {}", sender, e.getMessage());
        }
    }

    public boolean isEmpty() {
        return senderMonthCounts.isEmpty();
    }

    /**
     * Returns an immutable snapshot sorted by sender then by month.
     */
    public Map<String, Map<String, Integer>> snapshot() {
        Map<String, Map<String, Integer>> result = new LinkedHashMap<>();
        senderMonthCounts.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(senderEntry -> {
                    Map<String, Integer> months = new LinkedHashMap<>();
                    senderEntry.getValue().entrySet().stream()
                            .sorted(Map.Entry.comparingByKey())
                            .forEach(monthEntry -> months.put(monthEntry.getKey(), monthEntry.getValue().get()));
                    result.put(senderEntry.getKey(), months);
                });
        return result;
    }

    /**
     * Formats a date as "YYYY-MM" for sender statistics.
     */
    private static String formatYearMonth(Date date) {
        var cal = Calendar.getInstance();
        cal.setTime(date);
        return String.format("%04d-%02d", cal.get(Calendar.YEAR), cal.get(Calendar.MONTH) + 1);
    }
}
