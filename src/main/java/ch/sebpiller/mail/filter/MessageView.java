package ch.sebpiller.mail.filter;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * A read-only, filtering-oriented view of a single mail message. Implementations
 * extract each field lazily so that expensive work (decoding the body, walking
 * the MIME tree for attachments) only happens when a {@link MessageExclusion}
 * actually inspects it.
 */
public interface MessageView {

    /** The message sent date, or empty when absent/unreadable. */
    Optional<Instant> sentDate();

    /** The subject, or {@code ""} when absent/unreadable. */
    String subject();

    /** The {@code From} addresses (textual form); empty when none. */
    List<String> senders();

    /** All recipients ({@code To}/{@code Cc}/{@code Bcc}, textual form); empty when none. */
    List<String> recipients();

    /** The flattened textual body, or {@code ""} when unreadable. */
    String content();

    /** The message attachments (parts with a file name or attachment/inline disposition). */
    List<AttachmentView> attachments();
}
