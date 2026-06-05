package ch.sebpiller.mail.filter;

import java.util.function.Predicate;

/**
 * A named message-exclusion strategy backed by a {@link Predicate} over a
 * {@link MessageView}. Messages matching ANY configured exclusion are skipped
 * (never written to disk). This mirrors {@link FolderExclusion}, but operates on
 * individual messages rather than folders.
 *
 * <p>The factory methods cover the supported criteria:
 * <ul>
 *   <li>{@link #date(DateMatch)} &mdash; sent date;</li>
 *   <li>{@link #subject(TextMatch)} &mdash; subject;</li>
 *   <li>{@link #sender(TextMatch)} &mdash; any {@code From} address;</li>
 *   <li>{@link #recipient(TextMatch)} &mdash; any recipient address;</li>
 *   <li>{@link #content(TextMatch)} &mdash; the textual body;</li>
 *   <li>{@link #attachment(AttachmentMatch)} &mdash; any attachment.</li>
 * </ul>
 *
 * <pre>{@code
 * MessageExclusion.date(DateMatch.smallerThan(cutoff));
 * MessageExclusion.subject(TextMatch.regex("(?i)newsletter"));
 * MessageExclusion.sender(TextMatch.equalTo("no-reply@example.com").caseInsensitive());
 * MessageExclusion.attachment(AttachmentMatch.mimeType(TextMatch.regex("(?i)image/.*")));
 * }</pre>
 */
public record MessageExclusion(String description, Predicate<MessageView> predicate) {

    public boolean excludes(MessageView message) {
        return predicate.test(message);
    }

    /** Excludes a message whose sent date satisfies {@code match}. */
    public static MessageExclusion date(DateMatch match) {
        return new MessageExclusion("date " + match.description(),
                message -> message.sentDate().map(match::matches).orElse(false));
    }

    /** Excludes a message whose subject satisfies {@code match}. */
    public static MessageExclusion subject(TextMatch match) {
        return new MessageExclusion("subject " + match.description(),
                message -> match.matches(message.subject()));
    }

    /** Excludes a message any of whose {@code From} addresses satisfies {@code match}. */
    public static MessageExclusion sender(TextMatch match) {
        return new MessageExclusion("sender " + match.description(),
                message -> message.senders().stream().anyMatch(match::matches));
    }

    /** Excludes a message any of whose recipients satisfies {@code match}. */
    public static MessageExclusion recipient(TextMatch match) {
        return new MessageExclusion("recipient " + match.description(),
                message -> message.recipients().stream().anyMatch(match::matches));
    }

    /** Excludes a message whose textual body satisfies {@code match}. */
    public static MessageExclusion content(TextMatch match) {
        return new MessageExclusion("content " + match.description(),
                message -> match.matches(message.content()));
    }

    /** Excludes a message any of whose attachments satisfies {@code match}. */
    public static MessageExclusion attachment(AttachmentMatch match) {
        return new MessageExclusion("attachment " + match.description(),
                message -> message.attachments().stream().anyMatch(match::matches));
    }

}
