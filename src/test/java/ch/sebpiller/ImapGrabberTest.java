package ch.sebpiller;

import ch.sebpiller.mail.DownloadResult;
import ch.sebpiller.mail.MailDownloader;
import ch.sebpiller.mail.Mailbox;
import ch.sebpiller.mail.filter.*;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.TreeSet;

/**
 * Exercises the {@link MailDownloader} builder API end-to-end: it configures a
 * couple of IMAP mailboxes with folder-filtering options and downloads every
 * mail and attachment locally. This is an integration-style test that hits real
 * IMAP servers.
 *
 * <p>Connection details are <strong>not</strong> hard-coded here: they live in
 * {@code src/test/resources/mailboxes.properties} (git-ignored). Copy
 * {@code mailboxes.properties.example} to {@code mailboxes.properties} and fill
 * in real credentials. Add or remove a mailbox simply by adding or removing a
 * block of keys in that file - no change to this test is needed.
 */
@Disabled("DO NOT ENABLE - Not meant to be run automatically CI")
@Slf4j
public class ImapGrabberTest {

    /** Classpath location of the externalized connection details. */
    private static final String MAILBOXES_PROPERTIES = "/mailboxes.properties";

    private static List<Mailbox> mailboxes;

    @BeforeAll
    public static void setup() {
        mailboxes = loadMailboxes();
        log.info("Loaded {} mailbox(es) from {}", mailboxes.size(), MAILBOXES_PROPERTIES);
    }

    /**
     * Reads every mailbox declared in {@link #MAILBOXES_PROPERTIES}. Each mailbox
     * is a group of {@code mailbox.<name>.*} keys; the {@code <name>} is just a
     * label used to group host/port/username/password together.
     */
    private static List<Mailbox> loadMailboxes() {
        var props = new Properties();
        try (var in = ImapGrabberTest.class.getResourceAsStream(MAILBOXES_PROPERTIES)) {
            if (in == null) {
                throw new IllegalStateException(MAILBOXES_PROPERTIES + " not found on the classpath. "
                        + "Copy src/test/resources/mailboxes.properties.example to mailboxes.properties.");
            }
            props.load(in);
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to read " + MAILBOXES_PROPERTIES, e);
        }

        // Discover the distinct mailbox names from the "mailbox.<name>.host" keys.
        var names = new TreeSet<String>();
        for (var key : props.stringPropertyNames()) {
            if (key.startsWith("mailbox.") && key.endsWith(".host")) {
                names.add(key.substring("mailbox.".length(), key.length() - ".host".length()));
            }
        }

        List<Mailbox> result = new ArrayList<>();
        for (var name : names) {
            var prefix = "mailbox." + name + ".";
            var box = Mailbox.builder()
                    .host(props.getProperty(prefix + "host"))
                    .username(props.getProperty(prefix + "username"))
                    .password(props.getProperty(prefix + "password"));
            var port = props.getProperty(prefix + "port");
            if (port != null && !port.isBlank()) {
                box.port(Integer.parseInt(port.trim()));
            }
            result.add(box.build());
        }
        return result;
    }

    @Test
    public void testDownloadAllMails() {

        var result = MailDownloader.builder()
                .outputDirectory(Paths.get("all-my-mails"))
                .maxParallelMailboxes(4)
                .maxConsumersPerMailbox(8)
                // Incremental mode: the first run downloads everything and records a
                // per-folder UID high-water mark under <output>/.mail-sync-state; any
                // later run with the same output directory fetches only newer mail.
                .incremental(true)
                // The IMAP accounts to browse in parallel (loaded from mailboxes.properties).
                .mailboxes(mailboxes)
                // Folders matching ANY exclusion are skipped entirely.
                .excludeFolder(FolderExclusion.deeperThan(3))
                .excludeFolder(FolderExclusion.byName("Trash"))
                .excludeFolder(FolderExclusion.byName("Junk"))
                .excludeFolder(FolderExclusion.byName("Archives"))
                .excludeFolder(FolderExclusion.byRegex("(?i).*\\bspam\\b.*"))
                // Messages matching ANY exclusion are skipped (never written to disk).
                // Date: skip everything sent before 2015.
                .excludeMessage(MessageExclusion.date(
                        DateMatch.before(Instant.parse("2015-01-01T00:00:00Z"))))
                // Subject: skip newsletters (regex, case-insensitive by flag).
                .excludeMessage(MessageExclusion.subject(TextMatch.regex("(?i)newsletter")))
                // Sender: skip a specific address (strict, case-insensitive, trimmed).
                .excludeMessage(MessageExclusion.senderEmail(
                        TextMatch.equalTo("no-reply@example.com").caseInsensitive().trimmed()))
                // Recipient: skip mails addressed to a mailing list.
                .excludeMessage(MessageExclusion.recipient(TextMatch.regex("(?i)list@sebpiller\\.ch")))
                // Content: skip mails whose body mentions "unsubscribe".
                .excludeMessage(MessageExclusion.content(TextMatch.regex("(?i)unsubscribe")))
                // Attachments: skip mails carrying an image attachment.
                .excludeMessage(MessageExclusion.attachment(
                        AttachmentMatch.mimeType(TextMatch.regex("(?i)image/.*"))))
                // Attachments: skip mails carrying an image attachment.
                .excludeMessage(MessageExclusion.attachment(
                        AttachmentMatch.mimeType(TextMatch.regex("(?i)image/.*"))))
                .build()
                .run();

        log.info("Downloaded {} mail(s) and {} attachment(s), skipped {} message(s), in {}",
                result.mailsSaved(), result.attachmentsSaved(), result.messagesSkipped(), result.elapsed());
    }


}
