package ch.sebpiller;

import ch.sebpiller.mail.DownloadResult;
import ch.sebpiller.mail.MailDownloader;
import ch.sebpiller.mail.Mailbox;
import ch.sebpiller.mail.filter.*;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import java.nio.file.Paths;
import java.time.Instant;

/**
 * Exercises the {@link MailDownloader} builder API end-to-end: it configures a
 * couple of IMAP mailboxes with folder-filtering options and downloads every
 * mail and attachment locally. This is an integration-style test that hits real
 * IMAP servers using the credentials below.
 */
@Disabled("DO NOT ENABLE - Not meant to be run automatically CI")
@Slf4j
public class ImapGrabberTest {
    private static Mailbox infomaniak;
    private static Mailbox gmail;

    @BeforeAll
    public static void setup() {
         infomaniak = Mailbox.builder()
                .host("mail.infomaniak.ch").port(993)
                .username("me@sebpiller.ch").password("b65f0$.8hRHrU.K-")
                .build();
         gmail = Mailbox.builder()
                .host("imap.gmail.com").port(993)
                .username("piller.seb@gmail.com").password("tjhb oytj ovcv cqhx")
                .build();
    }

    @Test
    public void testDownloadAllMails() {

        DownloadResult result = MailDownloader.builder()
                .outputDirectory(Paths.get("target/all-mails"))
                .maxParallelMailboxes(4)
                .maxConsumersPerMailbox(8)
                // The IMAP accounts to browse in parallel.
                .mailbox(infomaniak)
                .mailbox(gmail)
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
                .excludeMessage(MessageExclusion.sender(
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
