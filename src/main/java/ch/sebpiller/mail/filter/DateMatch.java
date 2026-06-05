package ch.sebpiller.mail.filter;

import java.time.Instant;
import java.util.function.Predicate;

/**
 * Reusable, immutable matching rule for the date-oriented message criteria,
 * evaluated against a message's sent date.
 *
 * <pre>{@code
 * DateMatch.biggerThan(Instant.parse("2024-01-01T00:00:00Z"));   // newer than
 * DateMatch.smallerThan(Instant.parse("2020-01-01T00:00:00Z"));  // older than
 * DateMatch.between(lower, upper);                                // inclusive range
 * }</pre>
 */
public final class DateMatch {

    private final String description;
    private final Predicate<Instant> predicate;

    private DateMatch(String description, Predicate<Instant> predicate) {
        this.description = description;
        this.predicate = predicate;
    }

    /** Matches dates strictly after {@code threshold}. */
    public static DateMatch after(Instant threshold) {
        return new DateMatch("after " + threshold, date -> date.isAfter(threshold));
    }

    /** Matches dates strictly before {@code threshold}. */
    public static DateMatch before(Instant threshold) {
        return new DateMatch("before " + threshold, date -> date.isBefore(threshold));
    }

    /** Matches dates within the inclusive range {@code [lower, upper]}. */
    public static DateMatch between(Instant lower, Instant upper) {
        if (lower.isAfter(upper)) {
            throw new IllegalArgumentException("between(): lower " + lower + " is after upper " + upper);
        }
        return new DateMatch("between " + lower + " and " + upper,
                date -> !date.isBefore(lower) && !date.isAfter(upper));
    }

    /** Returns {@code true} when {@code date} satisfies this matcher. A {@code null} date never matches. */
    public boolean matches(Instant date) {
        return date != null && predicate.test(date);
    }

    public String description() {
        return description;
    }
}
