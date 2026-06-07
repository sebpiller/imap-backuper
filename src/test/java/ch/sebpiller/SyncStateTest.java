package ch.sebpiller;

import ch.sebpiller.mail.internal.SyncState;
import ch.sebpiller.mail.internal.SyncState.Key;
import ch.sebpiller.mail.internal.SyncState.Mark;
import ch.sebpiller.mail.internal.SyncStateStore;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Unit tests for the incremental high-water-mark logic, in particular the fix for
 * the bug where a single failing message pinned a folder's mark and forced every
 * later message to be re-downloaded on each run.
 */
class SyncStateTest {

    private static final String USER = "me@example.com";
    private static final String FOLDER = "Archives";
    private static final long VALIDITY = 1372845749L;

    @Test
    void aFailedMessageDoesNotHoldBackTheMark() {
        var state = new SyncState(Map.of(new Key(USER, FOLDER), new Mark(VALIDITY, 227, Set.of())));

        // A run resuming after UID 227 enqueues 228, 229, 230; message 228 fails.
        state.beginFolder(USER, FOLDER, VALIDITY, state.resumeAfterUid(USER, FOLDER, VALIDITY));
        state.recordEnqueued(USER, FOLDER, 228);
        state.recordEnqueued(USER, FOLDER, 229);
        state.recordEnqueued(USER, FOLDER, 230);
        state.recordFailure(USER, FOLDER, 228);

        var mark = state.snapshot().get(new Key(USER, FOLDER));
        assertEquals(230, mark.lastUid(), "the mark must advance past the failure, not stay pinned at 227");
        assertEquals(Set.of(228L), mark.failedUids(), "the failed UID is remembered for individual retry");
    }

    @Test
    void nextRunRetriesOnlyTheFailedUidAndFetchesNothingElse() {
        var previous = new SyncState(Map.of(new Key(USER, FOLDER), new Mark(VALIDITY, 230, Set.of(228L))));

        // Same validity: resume after the advanced mark, retry only the failed UID.
        assertEquals(230, previous.resumeAfterUid(USER, FOLDER, VALIDITY));
        assertEquals(Set.of(228L), previous.retryUids(USER, FOLDER, VALIDITY));

        // Changed validity (folder recreated): full fetch, no stale retries.
        assertEquals(0, previous.resumeAfterUid(USER, FOLDER, 999));
        assertTrue(previous.retryUids(USER, FOLDER, 999).isEmpty());
    }

    @Test
    void aRetriedMessageThatSucceedsIsForgotten() {
        var state = new SyncState(Map.of(new Key(USER, FOLDER), new Mark(VALIDITY, 230, Set.of(228L))));

        // The retried message 228 is enqueued again and this time succeeds (no failure recorded).
        state.beginFolder(USER, FOLDER, VALIDITY, state.resumeAfterUid(USER, FOLDER, VALIDITY));

        var mark = state.snapshot().get(new Key(USER, FOLDER));
        assertEquals(230, mark.lastUid());
        assertTrue(mark.failedUids().isEmpty(), "a previously-failed UID that succeeds is dropped from the retry list");
    }

    @Test
    void unvisitedFoldersKeepTheirPendingRetries() {
        var state = new SyncState(Map.of(new Key(USER, "Untouched"), new Mark(VALIDITY, 50, Set.of(7L, 9L))));

        var mark = state.snapshot().get(new Key(USER, "Untouched"));
        assertEquals(50, mark.lastUid());
        assertEquals(Set.of(7L, 9L), mark.failedUids());
    }

    @Test
    void persistsAndReloadsMarksIncludingRetries(@TempDir Path tmp) {
        var file = tmp.resolve(".mail-sync-state");
        var state = new SyncState(Map.of(
                new Key(USER, "INBOX"), new Mark(VALIDITY, 9981, Set.of()),
                new Key(USER, FOLDER), new Mark(VALIDITY, 3923, Set.of(228L, 541L))));

        SyncStateStore.save(file, state);
        var reloaded = SyncStateStore.load(file);

        assertEquals(9981, reloaded.resumeAfterUid(USER, "INBOX", VALIDITY));
        assertEquals(Set.of(), reloaded.retryUids(USER, "INBOX", VALIDITY));
        assertEquals(3923, reloaded.resumeAfterUid(USER, FOLDER, VALIDITY));
        assertEquals(Set.of(228L, 541L), reloaded.retryUids(USER, FOLDER, VALIDITY));
    }
}
