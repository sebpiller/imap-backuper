package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.util.MailFiles;
import lombok.extern.slf4j.Slf4j;

import javax.mail.Message;
import javax.mail.MessagingException;
import javax.mail.Multipart;
import javax.mail.Part;
import javax.mail.internet.MimeUtility;
import java.io.IOException;
import java.io.UnsupportedEncodingException;
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
                ? decodeMimeHeader(message.getFrom()[0].toString())
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

        // Body text: write either a clean body.html or a body.txt, never a mix.
        var bodyContent = BodyExtractor.extract(message);
        var bodyFileName = bodyContent.hasHtml() ? "body.html" : "body.txt";
        Files.writeString(mailDir.resolve(bodyFileName), bodyContent.body());
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

        String filename;
        try {
            filename = part.getFileName();
        } catch (MessagingException e) {
            // getFileName() can throw (e.g. "Can't decode filename") on a malformed
            // encoded-word name. Such a part is still an attachment, so save it under a
            // fallback name rather than failing the whole message.
            log.debug("Could not read attachment filename: {}", e.getMessage());
            filename = "attachment";
        }
        if (filename == null || filename.isBlank()) {
            return;
        }

        // Filenames are often RFC 2047 encoded-words (e.g. "=?UTF-8?Q?facture=C3=A9.pdf?=");
        // decode before sanitizing so the file lands on disk under its real name.
        var safeName = MailFiles.sanitizeFileName(decodeMimeHeader(filename));
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

    /**
     * Decodes RFC 2047 encoded-word headers (subjects, sender names, filenames) into
     * plain Unicode. Returns the value unchanged when it is not encoded or cannot be
     * decoded, so a malformed header never aborts a download.
     */
    private static String decodeMimeHeader(String value) {
        if (value == null) {
            return null;
        }
        try {
            return MimeUtility.decodeText(value);
        } catch (UnsupportedEncodingException e) {
            return value;
        }
    }
}
