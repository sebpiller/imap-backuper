package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.Mailbox;

import javax.mail.Session;
import java.util.Properties;

/**
 * Creates IMAP-over-SSL {@link Session}s for a {@link Mailbox}.
 */
public final class MailSessions {

    static {
        // Read by JavaMail from global system properties (not the session). Be lenient
        // when decoding slightly non-compliant encoded-words so MimeUtility.decodeText
        // returns a best effort rather than throwing.
        //
        // NB: we deliberately do NOT set mail.mime.decodefilename=true. With that flag
        // Part.getFileName() *throws* "Can't decode filename" on a malformed encoded
        // name, which would abort the whole message; instead MessageWriter decodes the
        // raw filename itself and falls back gracefully.
        setDefault("mail.mime.decodetext.strict", "false");
    }

    private static void setDefault(String key, String value) {
        if (System.getProperty(key) == null) {
            System.setProperty(key, value);
        }
    }

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
