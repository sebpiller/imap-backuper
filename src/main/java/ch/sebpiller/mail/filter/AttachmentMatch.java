package ch.sebpiller.mail.filter;

import java.util.function.Predicate;

/**
 * A named matching rule over a single {@link AttachmentView}. The factory methods
 * target one piece of attachment metadata each &mdash; MIME type, content
 * disposition or file name &mdash; using a {@link TextMatch}.
 *
 * <p>Use with {@link MessageExclusion#attachment(AttachmentMatch)}; a message is
 * excluded when <em>any</em> of its attachments matches.
 *
 * <pre>{@code
 * AttachmentMatch.mimeType(TextMatch.regex("(?i)image/.*"));
 * AttachmentMatch.disposition(TextMatch.equalTo("attachment").caseInsensitive());
 * AttachmentMatch.name(TextMatch.regex("(?i)\\.zip$"));
 * }</pre>
 */
public record AttachmentMatch(String description, Predicate<AttachmentView> predicate) {


    public boolean matches(AttachmentView attachment) {
        return predicate.test(attachment);
    }

    /** Matches an attachment whose base MIME type satisfies {@code match}. */
    public static AttachmentMatch mimeType(TextMatch match) {
        return new AttachmentMatch("mime type " + match.description(), a -> match.matches(a.mimeType()));
    }

    /** Matches an attachment whose content disposition satisfies {@code match}. */
    public static AttachmentMatch disposition(TextMatch match) {
        return new AttachmentMatch("disposition " + match.description(), a -> match.matches(a.disposition()));
    }

    /** Matches an attachment whose file name satisfies {@code match}. */
    public static AttachmentMatch name(TextMatch match) {
        return new AttachmentMatch("name " + match.description(), a -> match.matches(a.fileName()));
    }

}
