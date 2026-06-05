package ch.sebpiller.mail.internal;

import javax.mail.Message;
import javax.mail.MessagingException;
import javax.mail.Multipart;
import javax.mail.Part;
import javax.mail.Header;
import javax.mail.internet.ContentType;
import javax.mail.internet.MimeUtility;
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

/**
 * Flattens the readable (non-attachment) parts of a MIME message into a single
 * text or HTML body, annotating non-trivial parts with section headers.
 */
public final class BodyExtractor {

    private BodyExtractor() {
    }

    /** The flattened body and whether any part of it was HTML. */
    public record BodyContent(String content, boolean html) {
    }

    public static BodyContent extract(Part part) throws MessagingException, IOException {
        var content = new StringBuilder();
        var sawHtml = appendBodyContent(part, content, "");
        return new BodyContent(content.toString(), sawHtml);
    }

    private static boolean appendBodyContent(Part part, StringBuilder target, String path)
            throws MessagingException, IOException {
        if (isAttachment(part)) {
            return false;
        }

        Object content;
        try {
            content = part.getContent();
        } catch (IOException | RuntimeException e) {
            appendRawReadablePart(part, target, path, e);
            return false;
        }

        if (content instanceof Multipart multipart) {

            var sawHtml = false;
            for (var i = 0; i < multipart.getCount(); i++) {
                var childPath = path.isBlank() ? String.valueOf(i + 1) : path + "." + (i + 1);
                sawHtml |= appendBodyContent(multipart.getBodyPart(i), target, childPath);
            }
            return sawHtml;
        }

        if (content instanceof Message nestedMessage) {
            appendSectionHeader(part, target, path);
            target.append("Nested message");
            var subject = nestedMessage.getSubject();
            if (subject != null && !subject.isBlank()) {
                target.append(": ").append(subject);
            }
            target.append("\n");
            return appendBodyContent(nestedMessage, target, path.isBlank() ? "message" : path + ".message");
        }

        if (content instanceof String string) {
            //  appendSectionHeader(part, target, path);
            target.append(string).append("\n");
            return part.isMimeType("text/html");
        }

        if (part.isMimeType("text/*")) {
            appendRawReadablePart(part, target, path, null);
            return part.isMimeType("text/html");
        }

        if (content != null) {
            appendSectionHeader(part, target, path);
            target.append("Non-text body part decoded as ")
                    .append(content.getClass().getName())
                    .append("\n")
                    .append(String.valueOf(content))
                    .append("\n");
        }
        return false;
    }

    private static boolean isAttachment(Part part) throws MessagingException {
        return Part.ATTACHMENT.equalsIgnoreCase(part.getDisposition());
    }

    private static void appendRawReadablePart(Part part, StringBuilder target, String path, Exception decodeError)
            throws MessagingException, IOException {
        appendSectionHeader(part, target, path);
        if (decodeError != null) {
            target.append("Decoded content unavailable: ")
                    .append(decodeError.getMessage())
                    .append("\n");
        }
        try (var input = part.getInputStream()) {
            target.append(new String(input.readAllBytes(), charsetFor(part))).append("\n");
        } catch (IOException e) {
            target.append("Raw content unavailable: ").append(e.getMessage()).append("\n");
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

    private static void appendSectionHeader(Part part, StringBuilder target, String path) throws MessagingException {
        if (!target.isEmpty()) {
            target.append("\n");
        }
        target.append("===== body");
        if (path != null && !path.isBlank()) {
            target.append(".").append(path);
        }
        target.append(" =====\n");
        target.append("Content-Type: ").append(part.getContentType()).append("\n");
        var disposition = part.getDisposition();
        if (disposition != null && !disposition.isBlank()) {
            target.append("Disposition: ").append(disposition).append("\n");
        }
        var filename = part.getFileName();
        if (filename != null && !filename.isBlank()) {
            target.append("Filename: ").append(decodeHeader(filename)).append("\n");
        }
        target.append("Headers:\n").append(formatHeaders(part.getAllHeaders()));
        target.append("\n");
    }

    private static String decodeHeader(String value) {
        try {
            return MimeUtility.decodeText(value);
        } catch (Exception e) {
            return value;
        }
    }

    /**
     * Formats mail headers as a string for logging or content extraction.
     */
    private static String formatHeaders(Enumeration<Header> headers) {
        if (headers == null) {
            return "";
        }
        var sb = new StringBuilder();
        while (headers.hasMoreElements()) {
            var header = headers.nextElement();
            sb.append(header.getName()).append(": ").append(header.getValue()).append("\n");
        }
        return sb.toString();
    }
}
