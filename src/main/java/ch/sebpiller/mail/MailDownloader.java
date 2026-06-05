package ch.sebpiller.mail;

import ch.sebpiller.mail.filter.FolderExclusion;
import ch.sebpiller.mail.filter.MessageExclusion;
import ch.sebpiller.mail.internal.DomainStatisticsCollector;
import ch.sebpiller.mail.internal.DownloadStatistics;
import ch.sebpiller.mail.internal.FolderScanner;
import ch.sebpiller.mail.internal.MailboxDownloader;
import ch.sebpiller.mail.internal.MessageFilter;
import ch.sebpiller.mail.internal.MessageWriter;
import ch.sebpiller.mail.internal.ProgressReporter;
import lombok.SneakyThrows;
import lombok.extern.slf4j.Slf4j;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * Downloads every message (and its attachments) of one or more {@link Mailbox}es
 * to a local directory tree, laid out as
 * {@code <output>/<domain>/<sender>/<year>/<month>/<n>/}.
 *
 * <p>Configure and run with the fluent {@link #builder()}:
 * <pre>{@code
 * DownloadResult result = MailDownloader.builder()
 *         .outputDirectory(Paths.get("target/all-mails"))
 *         .maxParallelMailboxes(4)
 *         .maxConsumersPerMailbox(8)
 *         .mailbox(Mailbox.builder()
 *                 .host("imap.gmail.com").username("me@gmail.com").password("...")
 *                 .build())
 *         .excludeFolder(FolderExclusion.deeperThan(3))
 *         .excludeFolder(FolderExclusion.byName("Trash"))
 *         .excludeFolder(FolderExclusion.byRegex("(?i).*\\bspam\\b.*"))
 *         .build()
 *         .run();
 * }</pre>
 */
@Slf4j
public final class MailDownloader {

    private final List<Mailbox> mailboxes;
    private final Path outputDirectory;
    private final int maxParallelMailboxes;
    private final int maxConsumersPerMailbox;
    private final List<FolderExclusion> folderExclusions;
    private final List<MessageExclusion> messageExclusions;

    private MailDownloader(Builder builder) {
        this.mailboxes = List.copyOf(builder.mailboxes);
        this.outputDirectory = builder.outputDirectory;
        this.maxParallelMailboxes = builder.maxParallelMailboxes;
        this.maxConsumersPerMailbox = builder.maxConsumersPerMailbox;
        this.folderExclusions = List.copyOf(builder.folderExclusions);
        this.messageExclusions = List.copyOf(builder.messageExclusions);
    }

    public static Builder builder() {
        return new Builder();
    }

    /**
     * Downloads all configured mailboxes in parallel and returns a summary once
     * every mailbox has finished.
     */
    @SneakyThrows
    public DownloadResult run() {
        var outputDir = createOutputDirectory();
        var statistics = new DownloadStatistics();
        var folderScanner = new FolderScanner(folderExclusions);
        var messageWriter = new MessageWriter(outputDir, statistics);
        var messageFilter = new MessageFilter(messageExclusions);

        log.info("Starting full mail download from {} mailbox(es) into {}", mailboxes.size(), outputDir);
        var startNanos = System.nanoTime();

        try (var ignored = ProgressReporter.start(statistics, startNanos, 10)) {
            var mailboxThreads = Math.min(mailboxes.size(), maxParallelMailboxes);
            var executor = Executors.newFixedThreadPool(mailboxThreads);
            try {
                List<CompletableFuture<?>> futures = new ArrayList<>(mailboxes.size());
                for (var mailbox : mailboxes) {
                    var downloader = new MailboxDownloader(
                            mailbox, folderScanner, messageWriter, messageFilter, statistics, maxConsumersPerMailbox);
                    futures.add(CompletableFuture.runAsync(downloader::download, executor));
                }
                CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new)).join();
            } finally {
                executor.shutdown();
                if (!executor.awaitTermination(30, TimeUnit.MINUTES)) {
                    log.warn("Timed out waiting for mailbox tasks to terminate; forcing shutdown");
                    executor.shutdownNow();
                }
            }
        }

        var elapsed = Duration.ofNanos(System.nanoTime() - startNanos);
        var result = new DownloadResult(
                statistics.mailsSaved(),
                statistics.attachmentsSaved(),
                statistics.messagesSkipped(),
                elapsed,
                statistics.senderStatistics().snapshot(),
                DomainStatisticsCollector.collect(outputDir));
        result.logSummary();
        return result;
    }

    private Path createOutputDirectory() {
        try {
            Files.createDirectories(outputDirectory);
            return outputDirectory;
        } catch (IOException e) {
            throw new RuntimeException("Could not create output directory " + outputDirectory, e);
        }
    }

    /** Fluent builder for a {@link MailDownloader}. */
    public static final class Builder {
        private final List<Mailbox> mailboxes = new ArrayList<>();
        private final List<FolderExclusion> folderExclusions = new ArrayList<>();
        private final List<MessageExclusion> messageExclusions = new ArrayList<>();
        private Path outputDirectory = Path.of("target", "all-mails");
        // Upper bound on how many mailboxes are browsed at once
        private int maxParallelMailboxes = 4;
        // Upper bound on how many folders of a single mailbox are browsed at once.
        // Each folder worker needs its own IMAP connection, so this also bounds the
        // number of simultaneous connections opened per account.
        private int maxConsumersPerMailbox = 8;

        private Builder() {
        }

        /** Adds one mailbox to download. */
        public Builder mailbox(Mailbox mailbox) {
            this.mailboxes.add(mailbox);
            return this;
        }

        /** Adds several mailboxes to download. */
        public Builder mailboxes(List<Mailbox> mailboxes) {
            this.mailboxes.addAll(mailboxes);
            return this;
        }

        /** Local directory the mail tree is written into (created if missing). */
        public Builder outputDirectory(Path outputDirectory) {
            this.outputDirectory = outputDirectory;
            return this;
        }

        /** Upper bound on how many mailboxes are downloaded at once. */
        public Builder maxParallelMailboxes(int maxParallelMailboxes) {
            this.maxParallelMailboxes = maxParallelMailboxes;
            return this;
        }

        /** Upper bound on concurrent folder workers (IMAP connections) per mailbox. */
        public Builder maxConsumersPerMailbox(int maxConsumersPerMailbox) {
            this.maxConsumersPerMailbox = maxConsumersPerMailbox;
            return this;
        }

        /** Adds a folder-exclusion strategy; folders matching ANY exclusion are skipped. */
        public Builder excludeFolder(FolderExclusion exclusion) {
            this.folderExclusions.add(exclusion);
            return this;
        }

        /** Adds a message-exclusion strategy; messages matching ANY exclusion are skipped. */
        public Builder excludeMessage(MessageExclusion exclusion) {
            this.messageExclusions.add(exclusion);
            return this;
        }

        public MailDownloader build() {
            if (mailboxes.isEmpty()) {
                throw new IllegalStateException("At least one mailbox must be configured");
            }
            if (outputDirectory == null) {
                throw new IllegalStateException("An output directory must be configured");
            }
            if (maxParallelMailboxes < 1) {
                throw new IllegalStateException("maxParallelMailboxes must be >= 1, was " + maxParallelMailboxes);
            }
            if (maxConsumersPerMailbox < 1) {
                throw new IllegalStateException("maxConsumersPerMailbox must be >= 1, was " + maxConsumersPerMailbox);
            }
            return new MailDownloader(this);
        }
    }
}
