package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.filter.MessageExclusion;
import ch.sebpiller.mail.filter.MessageView;

import java.util.List;

/**
 * Holds the configured {@link MessageExclusion}s and decides whether a message
 * should be skipped. A message is excluded when it matches ANY exclusion.
 */
public final class MessageFilter {

    private final List<MessageExclusion> exclusions;

    public MessageFilter(List<MessageExclusion> exclusions) {
        this.exclusions = List.copyOf(exclusions);
    }

    public boolean isEmpty() {
        return exclusions.isEmpty();
    }

    /**
     * Returns the first exclusion that matches the message, or {@code null} when
     * the message should be processed.
     */
    public MessageExclusion firstMatchingExclusion(MessageView message) {
        for (var exclusion : exclusions) {
            if (exclusion.excludes(message)) {
                return exclusion;
            }
        }
        return null;
    }
}
