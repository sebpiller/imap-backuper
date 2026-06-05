package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.filter.AttachmentView;
import ch.sebpiller.mail.filter.MessageView;
import lombok.extern.slf4j.Slf4j;

import javax.mail.Message;
import javax.mail.MessagingException;
import javax.mail.Multipart;
import javax.mail.Part;
import javax.mail.internet.ContentType;
import javax.mail.internet.MimeUtility;
import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

/**
 * A {@link MessageView} backed by a live {@link Message}. Every field is computed
 * once on first access and memoized, and all extraction errors are swallowed
 * (logged at debug) so that a malformed message never breaks filtering.
 */
@Slf4j
public final class MailMessageView implements MessageView {

    private final Message message;

    private Optional<Instant> sentDate;
    private String subject;
    private List<String> senders;
    private List<String> recipients;
    private String content;
    private List<AttachmentView> attachments;

    public MailMessageView(Message message) {
        this.message = message;
    }

    @Override
    public Optional<Instant> sentDate() {
        if (sentDate == null) {
            sentDate = Optional.empty();
            try {
                var date = message.getSentDate();
                if (date != null) {
                    sentDate = Optional.of(date.toInstant());
                }
            } catch (MessagingException e) {
                log.debug("Could not read sent date: {}", e.getMessage());
            }
        }
        return sentDate;
    }

    @Override
    public String subject() {
        if (subject == null) {
            try {
                var value = message.getSubject();
                subject = value != null ? value : "";
            } catch (MessagingException e) {
                log.debug("Could not read subject: {}", e.getMessage());
                subject = "";
            }
        }
        return subject;
    }

    @Override
    public List<String> senders() {
        if (senders == null) {
            try {
                var from = message.getFrom();
                senders = from == null ? List.of()
                        : Arrays.stream(from).map(Object::toString).toList();
            } catch (MessagingException e) {
                log.debug("Could not read senders: {}", e.getMessage());
                senders = List.of();
            }
        }
        return senders;
    }

    @Override
    public List<String> recipients() {
        if (recipients == null) {
            try {
                var all = message.getAllRecipients();
                recipients = all == null ? List.of()
                        : Arrays.stream(all).map(Object::toString).toList();
            } catch (MessagingException e) {
                log.debug("Could not read recipients: {}", e.getMessage());
                recipients = List.of();
            }
        }
        return recipients;
    }

    @Override
    public String content() {
        if (content == null) {
            try {
                content = BodyExtractor.extract(message).content();
            } catch (MessagingException | IOException | RuntimeException e) {
                log.debug("Could not extract body content: {}", e.getMessage());
                content = "";
            }
        }
        return content;
    }

    @Override
    public List<AttachmentView> attachments() {
        if (attachments == null) {
            var collected = new ArrayList<AttachmentView>();
            try {
                collectAttachments(message, collected);
            } catch (MessagingException | IOException | RuntimeException e) {
                log.debug("Could not enumerate attachments: {}", e.getMessage());
            }
            attachments = List.copyOf(collected);
        }
        return attachments;
    }

    private void collectAttachments(Part part, List<AttachmentView> out) throws MessagingException, IOException {
        Object partContent;
        try {
            partContent = part.getContent();
        } catch (IOException | RuntimeException e) {
            // Undecodable parts still expose their headers below.
            partContent = null;
        }

        if (partContent instanceof Multipart multipart) {
            for (var i = 0; i < multipart.getCount(); i++) {
                collectAttachments(multipart.getBodyPart(i), out);
            }
            return;
        }

        var disposition = part.getDisposition();
        var fileName = decodeName(part.getFileName());
        var isAttachmentLike = (fileName != null && !fileName.isBlank())
                || Part.ATTACHMENT.equalsIgnoreCase(disposition)
                || Part.INLINE.equalsIgnoreCase(disposition);
        if (isAttachmentLike) {
            out.add(new AttachmentView(baseMimeType(part), disposition, fileName));
        }
    }

    private static String baseMimeType(Part part) throws MessagingException {
        var contentType = part.getContentType();
        try {
            return new ContentType(contentType).getBaseType();
        } catch (Exception e) {
            return contentType;
        }
    }

    private static String decodeName(String value) {
        if (value == null) {
            return null;
        }
        try {
            return MimeUtility.decodeText(value);
        } catch (Exception e) {
            return value;
        }
    }
}
