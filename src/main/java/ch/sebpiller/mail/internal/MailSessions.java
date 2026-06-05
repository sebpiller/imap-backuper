package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.Mailbox;

import javax.mail.Session;
import java.util.Properties;

/**
 * Creates IMAP-over-SSL {@link Session}s for a {@link Mailbox}.
 */
public final class MailSessions {

    private MailSessions() {
    }

    /**
     * Builds an IMAP-over-SSL mail session for the given mailbox.
     *
     * <p>The properties use the {@code mail.imaps.*} prefix to match the
     * {@code "imaps"} store protocol used by the downloader (a previous
     * {@code mail.imap.*} prefix was silently ignored). The configured host is
     * added to {@code mail.imaps.ssl.trust} so self-signed or self-hosted IMAP
     * servers (and test servers such as GreenMail) can be reached.
     */
    public static Session create(Mailbox mailbox) {
        var props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.host", mailbox.host());
        props.put("mail.imaps.port", String.valueOf(mailbox.port()));
        props.put("mail.imaps.ssl.enable", "true");
        props.put("mail.imaps.ssl.trust", mailbox.host());
        props.put("mail.imaps.auth.login.disable", "false");
        props.put("mail.imaps.auth.plain.disable", "false");
        return Session.getInstance(props, null);
    }
}
