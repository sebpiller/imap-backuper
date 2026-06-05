package ch.sebpiller.mail.filter;

import lombok.val;

import java.util.function.Predicate;

public final class IntMatch {

    private final Predicate<Integer> test;

    private IntMatch(Predicate<Integer> test) {
        this.test = test;
    }

    public static IntMatch equalTo(Integer value) {
        return new IntMatch(value::equals);
    }

    public static IntMatch equalsOrLess(int i) {
        return new IntMatch(v -> v <= i);
    }

    /**
     * Returns {@code true} when {@code candidate} satisfies this matcher. A
     * {@code null} candidate never matches.
     */
    public boolean matches(Integer candidate) {
        if (candidate == null) {
            return false;
        }

        return test.test(candidate);
    }

    /**
     * Human-readable description used by the exclusion descriptions.
     */
    public String description() {
        return test + "";
    }
}
