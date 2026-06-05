package ch.sebpiller.mail.filter;

/**
 * The metadata of a single message attachment as seen by {@link AttachmentMatch}:
 * its base MIME type (e.g. {@code "application/pdf"}), its content disposition
 * (e.g. {@code "attachment"} / {@code "inline"}) and its file name. Any field may
 * be {@code null} when the part does not declare it.
 */
public record AttachmentView(String mimeType, String disposition, String fileName) {
}
