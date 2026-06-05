package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.Mailbox;
import lombok.SneakyThrows;
import lombok.extern.slf4j.Slf4j;

import javax.mail.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Downloads every message of a single {@link Mailbox} using one producer that
 * enumerates folders and enqueues message references, and several consumers that
 * each keep their own IMAP connection open while writing messages to disk.
 */
@Slf4j
public final class MailboxDownloader {

    /**
     * A reference to a message to (re-)fetch: its folder, message number and UID (or -1).
     */
    private record DownloadMailRef(String folderName, int messageNumber, long uid) {
    }

    private final Mailbox mailbox;
    private final FolderScanner folderScanner;
    private final MessageWriter messageWriter;
    private final MessageFilter messageFilter;
    private final DownloadStatistics statistics;
    private final int maxConsumers;

    public MailboxDownloader(Mailbox mailbox, FolderScanner folderScanner, MessageWriter messageWriter,
                             MessageFilter messageFilter, DownloadStatistics statistics, int maxConsumers) {
        this.mailbox = mailbox;
        this.folderScanner = folderScanner;
        this.messageWriter = messageWriter;
        this.messageFilter = messageFilter;
        this.statistics = statistics;
        this.maxConsumers = maxConsumers;
    }

    /**
     * Connects to the mailbox and downloads every message using one producer and
     * several consumers, each with its own IMAP connection.
     */
    @SneakyThrows
    public void download() {
        Thread.currentThread().setName("dl-" + mailbox.username());
        log.info("Connecting to IMAP server {}:{} as {}", mailbox.host(), mailbox.port(), mailbox.username());

        var session = MailSessions.create(mailbox);

        var queue = new LinkedBlockingQueue<DownloadMailRef>();
        var producerDone = new AtomicBoolean(false);
        var consumers = Math.max(1, maxConsumers);

        log.info("Downloading mailbox {} with 1 producer and {} consumer(s)", mailbox.username(), consumers);

        var executor = Executors.newFixedThreadPool(consumers + 1);
        try {
            List<CompletableFuture<?>> futures = new ArrayList<>(consumers + 1);
            futures.add(CompletableFuture.runAsync(
                    () -> produceDownloadMailRefs(session, queue, producerDone), executor));

            for (var i = 1; i <= consumers; i++) {
                var consumerId = i;
                futures.add(CompletableFuture.runAsync(
                        () -> consumeDownloadMailRefs(session, queue, producerDone, consumerId),
                        executor));
            }

            CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new)).join();
        } finally {
            executor.shutdown();
            try {
                if (!executor.awaitTermination(30, TimeUnit.MINUTES)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException e) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }

        log.info("Finished downloading mailbox {}", mailbox.username());
    }

    @SneakyThrows
    private void produceDownloadMailRefs(Session session, BlockingQueue<DownloadMailRef> queue,
                                         AtomicBoolean producerDone) {
        Thread.currentThread().setName("dl-producer-" + mailbox.username());
        try {
            var store = session.getStore("imaps");
            try (store) {
                store.connect(mailbox.host(), mailbox.port(), mailbox.username(), mailbox.password());
                log.info("Producer connected to {}, enumerating folders", mailbox.username());

                var folderNames = folderScanner.collectMessageFolderNames(store.getDefaultFolder());
                if (folderNames.isEmpty()) {
                    log.info("No message-holding folders found in {}", mailbox.username());
                } else {
                    for (var folderName : folderNames) {
                        enqueueFolderMessages(store, folderName, queue);
                    }
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("Producer interrupted for mailbox {}", mailbox.username());
            throw e;
        } catch (Exception e) {
            log.error("Producer failed for mailbox {}: {}", mailbox.username(), e.getMessage(), e);
            throw e;
        } finally {
            producerDone.set(true);
            log.info("Producer finished for mailbox {}; {} queued item(s) still pending",
                    mailbox.username(), queue.size());
        }
    }

    private void enqueueFolderMessages(Store store, String folderName, BlockingQueue<DownloadMailRef> queue)
            throws MessagingException, InterruptedException {
        var folder = store.getFolder(folderName);
        log.debug("Producer scanning folder: {}", folderName);
        try {
            folder.open(Folder.READ_ONLY);
            var messages = folder.getMessages();
            statistics.addExpectedMessages(messages.length);
            log.info("Producer found {} messages in folder: {}", messages.length, folderName);
            for (var message : messages) {
                queue.put(new DownloadMailRef(folderName, message.getMessageNumber(), uidOf(folder, message)));
            }
        } finally {
            if (folder.isOpen()) {
                folder.close();
            }
        }
    }

    private long uidOf(Folder folder, Message message) {
        if (folder instanceof UIDFolder uidFolder) {
            try {
                return uidFolder.getUID(message);
            } catch (MessagingException e) {
                log.debug("Could not read UID for message {} in folder {}: {}",
                        message.getMessageNumber(), folder.getFullName(), e.getMessage());
            }
        }
        return -1;
    }

    private void consumeDownloadMailRefs(Session session, BlockingQueue<DownloadMailRef> queue,
                                         AtomicBoolean producerDone, int consumerId) {
        Thread.currentThread().setName("dl-consumer-" + consumerId + "-" + mailbox.username());
        Folder currentFolder = null;
        var currentFolderName = "";

        try (var store = session.getStore("imaps")) {
            store.connect(mailbox.host(), mailbox.port(), mailbox.username(), mailbox.password());
            log.info("Consumer {} connected for mailbox {}", consumerId, mailbox.username());

            while (!producerDone.get() || !queue.isEmpty()) {
                var mailRef = queue.poll();
                if (mailRef == null) {
                    sleepBeforeNextPoll();
                    continue;
                }

                try {
                    if (currentFolder == null || !mailRef.folderName().equals(currentFolderName)) {
                        currentFolder = switchOpenFolder(store, currentFolder, mailRef.folderName());
                        currentFolderName = mailRef.folderName();
                    }
                    var message = fetchMessage(currentFolder, mailRef);
                    var exclusion = messageFilter.firstMatchingExclusion(new MailMessageView(message));
                    if (exclusion != null) {
                        statistics.recordMessageSkipped();
                        log.info("Consumer {} skipped message {} from folder '{}' of mailbox {}: excluded by [{}]",
                                consumerId, mailRef.messageNumber(), mailRef.folderName(),
                                mailbox.username(), exclusion.description());
                        continue;
                    }
                    messageWriter.write(message);
                } catch (Exception e) {
                    log.warn("Consumer {} failed saving message {} from folder '{}' of mailbox {}: {}",
                            consumerId, mailRef.messageNumber(), mailRef.folderName(),
                            mailbox.username(), e.getMessage());
                }
            }

        } catch (MessagingException e) {
            log.error("Consumer {} failed for mailbox {}: {}", consumerId, mailbox.username(), e.getMessage(), e);
        } finally {
            closeFolder(currentFolder);
            log.info("Consumer {} finished for mailbox {}", consumerId, mailbox.username());
        }
    }

    private Folder switchOpenFolder(Store store, Folder currentFolder, String folderName) throws MessagingException {
        closeFolder(currentFolder);
        var nextFolder = store.getFolder(folderName);
        nextFolder.open(Folder.READ_ONLY);
        return nextFolder;
    }

    private Message fetchMessage(Folder folder, DownloadMailRef mailRef) throws MessagingException {
        if (mailRef.uid() >= 0 && folder instanceof UIDFolder uidFolder) {
            var message = uidFolder.getMessageByUID(mailRef.uid());
            if (message != null) {
                return message;
            }
            log.debug("Could not refetch UID {} in folder {}; falling back to message number {}",
                    mailRef.uid(), mailRef.folderName(), mailRef.messageNumber());
        }
        return folder.getMessage(mailRef.messageNumber());
    }

    private void sleepBeforeNextPoll() {
        try {
            Thread.sleep(500);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private void closeFolder(Folder folder) {
        if (folder == null) {
            return;
        }
        try {
            if (folder.isOpen()) {
                folder.close();
            }
        } catch (MessagingException e) {
            log.debug("Error closing folder {}: {}", folder.getFullName(), e.getMessage());
        }
    }
}
