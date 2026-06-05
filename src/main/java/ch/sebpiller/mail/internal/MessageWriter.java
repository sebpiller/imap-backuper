package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.util.MailFiles;
import lombok.extern.slf4j.Slf4j;

import javax.mail.Message;
import javax.mail.MessagingException;
import javax.mail.Multipart;
import javax.mail.Part;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Calendar;

/**
 * Writes a single message to disk under
 * {@code <root>/<domain>/<sender>/<year>/<month>/<n>/}: the flattened body goes
 * into {@code body.txt}/{@code body.html} and every attachment is written beside
 * it under its original (sanitized, de-duplicated) name.
 */
@Slf4j
public final class MessageWriter {

    private final Path root;
    private final DownloadStatistics statistics;

    public MessageWriter(Path root, DownloadStatistics statistics) {
        this.root = root;
        this.statistics = statistics;
    }

    /**
     * Stores a single message under "sender/year/month/mailNumber/": the text
     * body goes into body.txt and every attachment is written beside it under
     * its original name.
     */
    public void write(Message message) throws MessagingException, IOException {
        var from = message.getFrom() != null && message.getFrom().length > 0
                ? message.getFrom()[0].toString()
                : "Unknown";

        var sentDate = message.getSentDate();
        var calendar = Calendar.getInstance();
        if (sentDate != null) {
            calendar.setTime(sentDate);
        }
        var year = String.valueOf(calendar.get(Calendar.YEAR));
        var month = String.format("%02d", calendar.get(Calendar.MONTH) + 1);

        var monthDir = root
                .resolve(MailFiles.extractDomain(from))
                .resolve(MailFiles.sanitizeFileName(from))
                .resolve(year)
                .resolve(month);
        Files.createDirectories(monthDir);

        // Atomically claim a unique numbered directory for this mail so that
        // concurrent folder/mailbox threads never collide.
        Path mailDir;
        var mailNumber = 1;
        while (true) {
            mailDir = monthDir.resolve(String.valueOf(mailNumber));
            try {
                Files.createDirectory(mailDir);
                break;
            } catch (FileAlreadyExistsException e) {
                mailNumber++;
            }
        }

        // Body text
        var bodyContent = BodyExtractor.extract(message);
        var bodyFileName = bodyContent.html() ? "body.html" : "body.txt";
        Files.writeString(mailDir.resolve(bodyFileName), bodyContent.content());
        // Attachments
        saveAttachmentsToDir(message, mailDir);

        statistics.trackSender(message, from);

        var saved = statistics.recordMailSaved();
        log.info("Saved mail [#{}]: '{}' from {} -> {}",
                saved, message.getSubject() != null ? message.getSubject() : "", from, mailDir);
    }

    /**
     * Recursively walks a part's MIME tree and writes every part that has a
     * filename (i.e. any attachment, inline or not) into the given directory,
     * de-duplicating names on collision.
     */
    private void saveAttachmentsToDir(Part part, Path mailDir) throws MessagingException, IOException {
        Object content;
        try {
            content = part.getContent();
        } catch (IOException e) {
            // Some parts cannot be decoded; fall back to raw stream below.
            content = null;
        }

        if (content instanceof Multipart multipart) {
            for (var i = 0; i < multipart.getCount(); i++) {
                saveAttachmentsToDir(multipart.getBodyPart(i), mailDir);
            }
            return;
        }

        var filename = part.getFileName();
        if (filename == null || filename.isBlank()) {
            return;
        }

        var safeName = MailFiles.sanitizeFileName(filename);
        var dot = safeName.lastIndexOf('.');
        var baseName = dot >= 0 ? safeName.substring(0, dot) : safeName;
        var extension = dot >= 0 ? safeName.substring(dot) : "";

        var targetFile = mailDir.resolve(safeName);
        OutputStream out = null;
        var counter = 1;
        while (out == null) {
            try {
                out = Files.newOutputStream(targetFile, StandardOpenOption.CREATE_NEW);
            } catch (FileAlreadyExistsException e) {
                targetFile = mailDir.resolve(baseName + "_" + counter + extension);
                counter++;
            }
        }

        try (var o = out; var is = part.getInputStream()) {
            is.transferTo(o);
            var saved = statistics.recordAttachmentSaved();
            log.info("Saved attachment [#{}]: {} -> {}", saved, filename, targetFile);
        }
    }
}
