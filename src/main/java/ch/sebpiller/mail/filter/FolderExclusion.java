package ch.sebpiller.mail.filter;

import java.util.function.Predicate;
import java.util.regex.Pattern;

/**
 * A named folder-exclusion strategy backed by a {@link Predicate} over a
 * {@link FolderInfo}. The factory methods provide the three supported
 * strategies; {@link #excludes(FolderInfo)} returns {@code true} when the
 * folder must be skipped.
 */
public record FolderExclusion(String description, Predicate<FolderInfo> predicate) {

    public boolean excludes(FolderInfo info) {
        return predicate.test(info);
    }

    /** Excludes a folder whose leaf or full name equals {@code name}, case-insensitively and trimmed. */
    public static FolderExclusion byName(String name) {
        var needle = name.strip();
        return new FolderExclusion(
                "name equals '" + needle + "' (case-insensitive)",
                info -> needle.equalsIgnoreCase(info.name().strip())
                        || needle.equalsIgnoreCase(info.fullName().strip()));
    }

    /** Excludes a folder whose full name matches the given regular expression. */
    public static FolderExclusion byRegex(String regex) {
        var pattern = Pattern.compile(regex);
        return new FolderExclusion(
                "full name matches /" + regex + "/",
                info -> pattern.matcher(info.fullName()).matches());
    }

    /** Excludes a folder nested deeper than {@code maxLevel} (top-level folders are level 1). */
    public static FolderExclusion deeperThan(int maxLevel) {
        return new FolderExclusion(
                "level > " + maxLevel,
                info -> info.level() > maxLevel);
    }
}
