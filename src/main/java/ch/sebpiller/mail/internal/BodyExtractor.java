package ch.sebpiller.mail.internal;

import javax.mail.Message;
import javax.mail.MessagingException;
import javax.mail.Multipart;
import javax.mail.Part;
import javax.mail.internet.ContentType;
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

/**
 * Flattens the readable (non-attachment) parts of a MIME message, keeping the
 * HTML and plain-text representations in <em>separate</em> buffers so the writer
 * can emit a clean {@code body.html} (when the mail provides HTML) or a
 * {@code body.txt} - never a mix of the two. For a {@code multipart/alternative}
 * part only the richest representation is kept, so the HTML body is not polluted
 * with the plain-text twin or with diagnostic markers.
 */
public final class BodyExtractor {

    private BodyExtractor() {
    }

    /**
     * The extracted body: the flattened plain-text representation and the
     * flattened HTML representation. Either may be empty.
     */
    public record BodyContent(String text, String html) {

        /** Whether an HTML representation is available (and should be written as {@code body.html}). */
        public boolean hasHtml() {
            return html != null && !html.isBlank();
        }

        /** The body to write to disk: the HTML when present, otherwise the plain text. */
        public String body() {
            return hasHtml() ? html : text;
        }

        /** Combined representation used for content-based filtering (sees both text and HTML). */
        public String content() {
            if (hasHtml()) {
                return text.isBlank() ? html : text + "\n" + html;
            }
            return text;
        }
    }

    public static BodyContent extract(Part part) throws MessagingException, IOException {
        var text = new StringBuilder();
        var html = new StringBuilder();
        append(part, text, html);
        return new BodyContent(text.toString(), html.toString());
    }

    private static void append(Part part, StringBuilder text, StringBuilder html)
            throws MessagingException, IOException {
        if (isAttachment(part)) {
            return;
        }

        Object content;
        try {
            content = part.getContent();
        } catch (IOException | RuntimeException e) {
            // Could not decode the part; fall back to its raw bytes.
            appendDecodedRaw(part, text, html);
            return;
        }

        if (content instanceof Multipart multipart) {
            if (isAlternative(part)) {
                appendAlternative(multipart, text, html);
            } else {
                for (var i = 0; i < multipart.getCount(); i++) {
                    append(multipart.getBodyPart(i), text, html);
                }
            }
            return;
        }

        if (content instanceof Message nested) {
            var subject = nested.getSubject();
            appendBlock(text, "Nested message" + (subject != null && !subject.isBlank() ? ": " + subject : ""));
            append(nested, text, html);
            return;
        }

        if (content instanceof String string) {
            appendBlock(isHtml(part) ? html : text, string);
            return;
        }

        if (part.isMimeType("text/*")) {
            appendDecodedRaw(part, text, html);
            return;
        }

        if (content != null) {
            appendBlock(text, "Non-text body part decoded as " + content.getClass().getName() + "\n" + content);
        }
    }

    /**
     * Handles a {@code multipart/alternative}: keeps only the richest representation.
     * The HTML alternative is preferred for {@code body.html}; the plain-text
     * alternative is still retained in the text buffer so content filtering can see
     * it, but it is never written into the HTML body.
     */
    private static void appendAlternative(Multipart multipart, StringBuilder text, StringBuilder html)
            throws MessagingException, IOException {
        StringBuilder bestHtml = null;
        StringBuilder bestText = null;
        for (var i = 0; i < multipart.getCount(); i++) {
            var partText = new StringBuilder();
            var partHtml = new StringBuilder();
            append(multipart.getBodyPart(i), partText, partHtml);
            if (!partHtml.isEmpty()) {
                bestHtml = partHtml; // prefer the last (richest) HTML alternative
            } else if (!partText.isEmpty() && (bestText == null || partText.length() > bestText.length())) {
                bestText = partText;
            }
        }
        if (bestText != null) {
            appendBlock(text, bestText.toString());
        }
        if (bestHtml != null) {
            appendBlock(html, bestHtml.toString());
        }
    }

    /** Appends a non-empty block to {@code target}, separating successive blocks with a blank line. */
    private static void appendBlock(StringBuilder target, String value) {
        if (value == null || value.isEmpty()) {
            return;
        }
        if (!target.isEmpty()) {
            target.append("\n");
        }
        target.append(value);
    }

    private static void appendDecodedRaw(Part part, StringBuilder text, StringBuilder html)
            throws MessagingException {
        var target = isHtml(part) ? html : text;
        try (var input = part.getInputStream()) {
            appendBlock(target, new String(input.readAllBytes(), charsetFor(part)));
        } catch (IOException e) {
            // Keep diagnostics out of the HTML body so it stays well-formed.
            if (target != html) {
                appendBlock(text, "Raw content unavailable: " + e.getMessage());
            }
        }
    }

    private static boolean isAttachment(Part part) throws MessagingException {
        return Part.ATTACHMENT.equalsIgnoreCase(part.getDisposition());
    }

    private static boolean isAlternative(Part part) {
        try {
            return part.isMimeType("multipart/alternative");
        } catch (MessagingException e) {
            return false;
        }
    }

    private static boolean isHtml(Part part) {
        try {
            return part.isMimeType("text/html");
        } catch (MessagingException e) {
            return false;
        }
    }

    private static Charset charsetFor(Part part) throws MessagingException {
        try {
            var charset = new ContentType(part.getContentType()).getParameter("charset");
            if (charset != null && !charset.isBlank()) {
                return Charset.forName(charset);
            }
        } catch (Exception ignored) {
            // Fall through to UTF-8 when the header is missing or malformed.
        }
        return StandardCharsets.UTF_8;
    }
}
