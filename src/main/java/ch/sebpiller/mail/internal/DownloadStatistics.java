package ch.sebpiller.mail.internal;

import javax.mail.Message;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Thread-safe counters shared by every mailbox/folder worker during a download:
 * how many mails and attachments have been saved, how many messages are expected
 * in total, and the per-sender monthly tally.
 */
public final class DownloadStatistics {

    private final AtomicInteger mailsSaved = new AtomicInteger();
    private final AtomicInteger attachmentsSaved = new AtomicInteger();
    private final AtomicInteger messagesSkipped = new AtomicInteger();
    private final AtomicInteger totalMessagesToProcess = new AtomicInteger();
    private final SenderStatistics senderStatistics = new SenderStatistics();

    /** Records that {@code count} more messages are expected; used for progress/ETA. */
    public void addExpectedMessages(int count) {
        totalMessagesToProcess.addAndGet(count);
    }

    /** Records one saved mail and returns the running total. */
    public int recordMailSaved() {
        return mailsSaved.incrementAndGet();
    }

    /** Records one saved attachment and returns the running total. */
    public int recordAttachmentSaved() {
        return attachmentsSaved.incrementAndGet();
    }

    /** Records one message skipped by a {@link MessageFilter} and returns the running total. */
    public int recordMessageSkipped() {
        return messagesSkipped.incrementAndGet();
    }

    public void trackSender(Message message, String sender) {
        senderStatistics.track(message, sender);
    }

    public int mailsSaved() {
        return mailsSaved.get();
    }

    public int attachmentsSaved() {
        return attachmentsSaved.get();
    }

    public int messagesSkipped() {
        return messagesSkipped.get();
    }

    public int totalMessagesToProcess() {
        return totalMessagesToProcess.get();
    }

    public SenderStatistics senderStatistics() {
        return senderStatistics;
    }
}
