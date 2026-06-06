package ch.sebpiller;

import ch.sebpiller.mail.DownloadResult;
import ch.sebpiller.mail.MailDownloader;
import ch.sebpiller.mail.Mailbox;
import com.icegreen.greenmail.user.GreenMailUser;
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Verifies the incremental-download feature against an in-process GreenMail IMAPS
 * server: the first run fetches every message and records a per-folder UID
 * high-water mark, and later runs fetch only the messages delivered since.
 *
 * <p>GreenMail speaks IMAP over the socket, so the production {@code javax.mail}
 * client interoperates with it even though GreenMail itself is built on
 * {@code jakarta.mail} (used here only to build and deliver the test messages).
 */
class IncrementalDownloadTest {

    private static final String EMAIL = "alice@localhost";
    private static final String LOGIN = "alice";
    private static final String PASSWORD = "secret";

    private GreenMail greenMail;
    private GreenMailUser user;
    private ServerSetup imaps;

    @BeforeEach
    void startServer() {
        imaps = ServerSetup.IMAPS.dynamicPort();
        greenMail = new GreenMail(imaps);
        greenMail.start();
        user = greenMail.setUser(EMAIL, LOGIN, PASSWORD);
    }

    @AfterEach
    void stopServer() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void incrementalRunsFetchOnlyNewMail(@TempDir Path tmp) throws Exception {
        var output = tmp.resolve("mails");
        var stateFile = tmp.resolve("sync-state");

        deliver("First subject", "first body");
        deliver("Second subject", "second body");

        var firstRun = run(output, stateFile);
        assertEquals(2, firstRun.mailsSaved(), "first run should download every message");
        assertTrue(Files.exists(stateFile), "the sync-state file should be written after a run");

        deliver("Third subject", "third body");

        var secondRun = run(output, stateFile);
        assertEquals(1, secondRun.mailsSaved(), "second run should download only the newly delivered message");

        var thirdRun = run(output, stateFile);
        assertEquals(0, thirdRun.mailsSaved(), "a run with no new mail should download nothing");
    }

    private DownloadResult run(Path output, Path stateFile) {
        var mailbox = Mailbox.builder()
                .host("localhost")
                .port(greenMail.getImaps().getPort())
                .username(LOGIN)
                .password(PASSWORD)
                .build();
        return MailDownloader.builder()
                .outputDirectory(output)
                .syncStateFile(stateFile)
                .incremental(true)
                .maxParallelMailboxes(1)
                .maxConsumersPerMailbox(1)
                .mailbox(mailbox)
                .build()
                .run();
    }

    /**
     * Delivers a message by parsing raw RFC822 bytes rather than setting a Java
     * object as content: GreenMail copies the message on delivery via
     * {@code writeTo}, and a parsed message streams its bytes without needing a
     * {@code DataContentHandler} - which avoids the javax/jakarta mailcap clash
     * caused by both mail flavours being on the test classpath.
     */
    private void deliver(String subject, String body) throws Exception {
        var raw = "From: " + EMAIL + "\r\n"
                + "To: " + EMAIL + "\r\n"
                + "Subject: " + subject + "\r\n"
                + "Content-Type: text/plain; charset=UTF-8\r\n"
                + "\r\n"
                + body + "\r\n";
        var in = new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8));
        var message = new MimeMessage((jakarta.mail.Session) null, in);
        user.deliver(message);
    }
}
