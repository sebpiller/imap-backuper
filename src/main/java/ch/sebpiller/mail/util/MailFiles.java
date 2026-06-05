package ch.sebpiller.mail.util;

/**
 * Small helpers for turning mail metadata into safe filesystem path segments.
 */
public final class MailFiles {

    private MailFiles() {
    }

    /**
     * Extracts the domain portion from an email address.
     * For example, "user@example.com" returns "example.com".
     * If no @ symbol is found, returns "unknown-domain".
     */
    public static String extractDomain(String email) {
        if (email == null || email.isBlank()) {
            return "unknown-domain";
        }
        var atIndex = email.lastIndexOf('@');
        if (atIndex < 0 || atIndex == email.length() - 1) {
            return "unknown-domain";
        }
        var domain = email.substring(atIndex + 1).trim();
        // Remove any angle brackets that might be present (e.g., "<user@example.com>")
        domain = domain.replaceAll("[<>]", "");
        return domain.isEmpty() ? "unknown-domain" : domain;
    }

    /**
     * Turns an arbitrary string (sender address, attachment name) into a safe
     * single path segment by replacing characters that are awkward in file
     * names. Never returns an empty string.
     */
    public static String sanitizeFileName(String name) {
        var cleaned = name.replaceAll("[\\\\/:*?\"<>|\\r\\n\\t]", "_").trim();
        if (cleaned.length() > 200) {
            cleaned = cleaned.substring(0, 200);
        }
        return cleaned.isEmpty() ? "unknown" : cleaned;
    }
}
