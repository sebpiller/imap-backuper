package ch.sebpiller.mail.filter;

/**
 * Identity of a folder as seen by the exclusion strategies: its full name
 * (e.g. {@code "[Gmail]/All Mail"}), its leaf name (e.g. {@code "All Mail"})
 * and its hierarchy level (top-level folders are level 1).
 */
public record FolderInfo(String fullName, String name, int level) {
}
