package ch.sebpiller.mail.filter;

import java.util.regex.Pattern;

/**
 * Reusable, immutable matching rule for the string-oriented message criteria
 * (subject, sender, recipient, content, attachment metadata).
 *
 * <p>Two modes are supported:
 * <ul>
 *   <li>{@link #equalTo(String)} &mdash; strict matching (the whole candidate
 *       must equal the target);</li>
 *   <li>{@link #regex(String)} &mdash; the candidate matches when the pattern is
 *       <em>found</em> anywhere in it (anchor with {@code ^…$} for a full match).</li>
 * </ul>
 *
 * <p>Both modes honour the configurable options, applied with fluent withers
 * that return a new instance:
 * <ul>
 *   <li>case sensitivity &mdash; {@link #caseSensitive(boolean)} /
 *       {@link #caseInsensitive()} (default: case-sensitive);</li>
 *   <li>auto-trim &mdash; {@link #autoTrim(boolean)} / {@link #trimmed()}, which
 *       strips leading/trailing whitespace from both sides before matching
 *       (default: off).</li>
 * </ul>
 *
 * <pre>{@code
 * TextMatch.equalTo("Invoice").caseInsensitive().trimmed();
 * TextMatch.regex("(?i)\\binvoice\\b");
 * }</pre>
 */
public final class TextMatch {

    private final String pattern;
    private final boolean regex;
    private final boolean caseSensitive;
    private final boolean autoTrim;
    private final Pattern compiled;

    private TextMatch(String pattern, boolean regex, boolean caseSensitive, boolean autoTrim) {
        this.pattern = pattern;
        this.regex = regex;
        this.caseSensitive = caseSensitive;
        this.autoTrim = autoTrim;
        this.compiled = regex
                ? Pattern.compile(pattern, caseSensitive ? 0 : Pattern.CASE_INSENSITIVE)
                : null;
    }

    /** Strict matcher: the candidate must equal {@code value}. */
    public static TextMatch equalTo(String value) {
        return new TextMatch(value, false, true, false);
    }

    /** Regex matcher: the candidate matches when {@code regex} is found in it. */
    public static TextMatch regex(String regex) {
        return new TextMatch(regex, true, true, false);
    }

    /** Returns a copy with the given case sensitivity. */
    public TextMatch caseSensitive(boolean caseSensitive) {
        return new TextMatch(pattern, regex, caseSensitive, autoTrim);
    }

    /** Returns a case-insensitive copy. */
    public TextMatch caseInsensitive() {
        return caseSensitive(false);
    }

    /** Returns a copy with the given auto-trim behaviour. */
    public TextMatch autoTrim(boolean autoTrim) {
        return new TextMatch(pattern, regex, caseSensitive, autoTrim);
    }

    /** Returns a copy that strips whitespace from both target and candidate before matching. */
    public TextMatch trimmed() {
        return autoTrim(true);
    }

    /**
     * Returns {@code true} when {@code candidate} satisfies this matcher. A
     * {@code null} candidate never matches.
     */
    public boolean matches(String candidate) {
        if (candidate == null) {
            return false;
        }
        var value = autoTrim ? candidate.strip() : candidate;
        if (regex) {
            return compiled.matcher(value).find();
        }
        var target = autoTrim ? pattern.strip() : pattern;
        return caseSensitive ? target.equals(value) : target.equalsIgnoreCase(value);
    }

    /** Human-readable description used by the exclusion descriptions. */
    public String description() {
        var options = new StringBuilder(caseSensitive ? "case-sensitive" : "case-insensitive");
        if (autoTrim) {
            options.append(", trimmed");
        }
        var base = regex ? "matches /" + pattern + "/" : "equals '" + pattern + "'";
        return base + " (" + options + ")";
    }
}
