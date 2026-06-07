package ch.sebpiller;

import ch.sebpiller.mail.internal.BodyExtractor;
import ch.sebpiller.mail.internal.DownloadStatistics;
import ch.sebpiller.mail.internal.MessageWriter;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.activation.DataHandler;
import javax.mail.Part;
import javax.mail.Session;
import javax.mail.internet.InternetAddress;
import javax.mail.internet.MimeBodyPart;
import javax.mail.internet.MimeMessage;
import javax.mail.internet.MimeMultipart;
import javax.mail.util.ByteArrayDataSource;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Date;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Unit tests for the two body/filename bugs, exercised on an in-memory MIME
 * message (no IMAP server needed):
 * <ol>
 *   <li>{@link BodyExtractor} keeps HTML and plain text apart, so a
 *       {@code multipart/alternative} mail produces a clean HTML body rather than
 *       the two alternatives concatenated with diagnostic markers;</li>
 *   <li>{@link MessageWriter} MIME-decodes attachment filenames before writing,
 *       so an RFC 2047 encoded-word name lands on disk as real Unicode.</li>
 * </ol>
 */
class BodyAndFilenameTest {

    /** RFC 2047 Q-encoded word that decodes to {@code facturé.pdf}. */
    private static final String ENCODED_FILENAME = "=?UTF-8?Q?factur=C3=A9.pdf?=";
    private static final String DECODED_FILENAME = "facturé.pdf";

    @Test
    void alternativeBodyKeepsOnlyTheHtmlRepresentation() throws Exception {
        var body = BodyExtractor.extract(buildMessage());

        assertTrue(body.hasHtml(), "an HTML alternative should be detected");
        assertTrue(body.html().contains("HTML_MARKER"), "HTML buffer holds the HTML alternative");
        assertFalse(body.html().contains("PLAINTEXT_MARKER"), "HTML buffer must not hold the plain-text twin");
        assertEquals(body.html(), body.body(), "the body written to disk is the HTML when present");

        // The plain text is still available for content-based filtering.
        assertTrue(body.content().contains("PLAINTEXT_MARKER"));
        assertTrue(body.content().contains("HTML_MARKER"));
    }

    @Test
    void writerEmitsCleanHtmlAndDecodesFilename(@TempDir Path tmp) throws Exception {
        new MessageWriter(tmp, new DownloadStatistics()).write(buildMessage());

        var htmlBody = Files.readString(findFile(tmp, "body.html"), StandardCharsets.UTF_8);
        assertTrue(htmlBody.contains("HTML_MARKER"), "body.html should contain the HTML alternative");
        assertTrue(htmlBody.contains("héllo"), "body.html should preserve UTF-8 content");
        assertFalse(htmlBody.contains("PLAINTEXT_MARKER"), "body.html must not contain the plain-text alternative");
        assertFalse(htmlBody.contains("Content-Type:"), "body.html must not contain MIME diagnostic dumps");
        assertFalse(htmlBody.contains("====="), "body.html must not contain section-header markers");

        var attachment = findFile(tmp, DECODED_FILENAME);
        assertEquals(DECODED_FILENAME, attachment.getFileName().toString(),
                "the attachment filename should be MIME-decoded on disk");
    }

    /**
     * Builds {@code multipart/mixed { multipart/alternative { text/plain, text/html },
     * pdf attachment }} entirely in memory. Content is stored as objects / a byte
     * {@link ByteArrayDataSource}, so reading it back never needs a MIME content
     * handler.
     */
    private static MimeMessage buildMessage() throws Exception {
        var alternative = new MimeMultipart("alternative");
        var plain = new MimeBodyPart();
        plain.setText("PLAINTEXT_MARKER plain alternative", "UTF-8");
        // Set the Content-Type header explicitly: without saveChanges() (which we avoid
        // so reading the message never invokes a MIME content handler) the part type
        // would otherwise default to text/plain and the HTML wouldn't be recognised.
        plain.setHeader("Content-Type", "text/plain; charset=UTF-8");
        var html = new MimeBodyPart();
        html.setContent("<html><body><p>HTML_MARKER héllo</p></body></html>", "text/html; charset=UTF-8");
        html.setHeader("Content-Type", "text/html; charset=UTF-8");
        alternative.addBodyPart(plain);
        alternative.addBodyPart(html);

        var alternativePart = new MimeBodyPart();
        alternativePart.setContent(alternative);

        var attachment = new MimeBodyPart();
        attachment.setDataHandler(new DataHandler(
                new ByteArrayDataSource("hello-pdf".getBytes(StandardCharsets.UTF_8), "application/pdf")));
        attachment.setFileName(ENCODED_FILENAME);
        attachment.setDisposition(Part.ATTACHMENT);

        var mixed = new MimeMultipart("mixed");
        mixed.addBodyPart(alternativePart);
        mixed.addBodyPart(attachment);

        var message = new MimeMessage((Session) null);
        message.setFrom(new InternetAddress("alice@example.com"));
        message.setSubject("Mixed body");
        message.setSentDate(new Date());
        message.setContent(mixed);
        return message;
    }

    /** Finds the single file with the given name anywhere under {@code root}. */
    private static Path findFile(Path root, String fileName) throws Exception {
        try (var paths = Files.walk(root)) {
            List<Path> matches = paths.filter(p -> p.getFileName().toString().equals(fileName)).toList();
            assertEquals(1, matches.size(),
                    "expected exactly one '" + fileName + "' under " + root + ", found " + matches);
            return matches.get(0);
        }
    }
}
