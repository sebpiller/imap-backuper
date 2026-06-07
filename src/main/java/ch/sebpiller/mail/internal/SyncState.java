package ch.sebpiller.mail.internal;

import lombok.extern.slf4j.Slf4j;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Thread-safe per-run state backing incremental downloads. For every folder it
 * remembers, keyed by {@code (username, folderFullName)}, the highest IMAP UID
 * that has been processed - the <em>high-water mark</em> - together with the
 * folder's {@code UIDVALIDITY} at the time the mark was taken, and the set of
 * UIDs that <em>failed</em> to download and should be retried.
 *
 * <p>A run starts from the marks {@linkplain SyncStateStore#load(java.nio.file.Path)
 * loaded} from the previous run. While the run proceeds:
 * <ul>
 *   <li>the producer calls {@link #resumeAfterUid} for the UID to resume after and
 *       {@link #retryUids} for previously-failed UIDs to re-fetch (both only when
 *       the folder's current {@code UIDVALIDITY} still matches the stored one),
 *       {@link #beginFolder} once before enqueuing, and {@link #recordEnqueued}
 *       for each <em>new</em> message it enqueues;</li>
 *   <li>a consumer calls {@link #recordFailure} when it fails to write a message.</li>
 * </ul>
 *
 * <p>{@link #snapshot()} then advances the mark to the highest UID enqueued this
 * run - <strong>regardless of failures</strong> - so a single message that keeps
 * failing can no longer pin a folder and force every later message to be
 * re-downloaded on each run. Instead the failing UIDs are recorded and retried
 * individually next time, without blocking progress.
 */
@Slf4j
public final class SyncState {

    /** Above this many persistently-failing messages in one folder we warn the operator. */
    private static final int FAILED_WARN_THRESHOLD = 1000;

    /** Identifies a folder within a mailbox. */
    public record Key(String username, String folderFullName) {
    }

    /**
     * A persisted mark: the folder's {@code UIDVALIDITY}, the high-water UID, and the
     * UIDs that failed to download and are awaiting retry.
     */
    public record Mark(long uidValidity, long lastUid, Set<Long> failedUids) {
        public Mark {
            failedUids = Set.copyOf(failedUids);
        }
    }

    /** Live, mutable tracking for a folder being processed during the current run. */
    private static final class FolderProgress {
        private final long uidValidity;
        private final AtomicLong maxEnqueued;
        private final Set<Long> failed = ConcurrentHashMap.newKeySet();

        private FolderProgress(long uidValidity, long carriedLastUid) {
            this.uidValidity = uidValidity;
            this.maxEnqueued = new AtomicLong(carriedLastUid);
        }
    }

    /** Marks carried over from the previous run (read-only during a run). */
    private final Map<Key, Mark> previous;
    /** Live progress for folders visited during the current run. */
    private final Map<Key, FolderProgress> current = new ConcurrentHashMap<>();

    public SyncState(Map<Key, Mark> previous) {
        this.previous = Map.copyOf(previous);
    }

    /** An empty state, as used by the very first (full) download. */
    public static SyncState empty() {
        return new SyncState(Map.of());
    }

    /**
     * Returns the UID to resume <em>after</em> for the given folder: the previous
     * run's high-water mark when {@code currentValidity} still matches the stored
     * {@code UIDVALIDITY}, or {@code 0} when there is no usable mark (no prior
     * state, or the folder was recreated and its validity changed - both call for
     * a full fetch).
     */
    public long resumeAfterUid(String username, String folderFullName, long currentValidity) {
        var mark = previous.get(new Key(username, folderFullName));
        return mark != null && mark.uidValidity() == currentValidity ? mark.lastUid() : 0L;
    }

    /**
     * Returns the UIDs that failed on a previous run and should be retried, when the
     * folder's {@code UIDVALIDITY} still matches; otherwise an empty set.
     */
    public Set<Long> retryUids(String username, String folderFullName, long currentValidity) {
        var mark = previous.get(new Key(username, folderFullName));
        return mark != null && mark.uidValidity() == currentValidity ? mark.failedUids() : Set.of();
    }

    /** Initializes live tracking for a folder before any message of it is enqueued. */
    public void beginFolder(String username, String folderFullName, long uidValidity, long carriedLastUid) {
        current.put(new Key(username, folderFullName), new FolderProgress(uidValidity, carriedLastUid));
    }

    /** Records that a new message with {@code uid} was enqueued for processing (atomic max). */
    public void recordEnqueued(String username, String folderFullName, long uid) {
        var progress = current.get(new Key(username, folderFullName));
        if (progress != null) {
            progress.maxEnqueued.accumulateAndGet(uid, Math::max);
        }
    }

    /** Records that processing a message with {@code uid} failed, so it is retried next run. */
    public void recordFailure(String username, String folderFullName, long uid) {
        var progress = current.get(new Key(username, folderFullName));
        if (progress != null) {
            progress.failed.add(uid);
        }
    }

    /**
     * Builds the marks to persist for the next run: every folder carried over from
     * the previous run (preserving its pending retries), overlaid with an advanced
     * mark for each folder visited this run. The mark advances to {@code maxEnqueued}
     * unconditionally; UIDs that failed this run are stored for individual retry.
     */
    public Map<Key, Mark> snapshot() {
        Map<Key, Mark> result = new ConcurrentHashMap<>(previous);
        current.forEach((key, progress) -> {
            var failed = Set.copyOf(progress.failed);
            if (failed.size() > FAILED_WARN_THRESHOLD) {
                log.warn("Folder '{}' of {} has {} message(s) that keep failing to download; "
                                + "they are retried on every incremental run",
                        key.folderFullName(), key.username(), failed.size());
            }
            result.put(key, new Mark(progress.uidValidity, progress.maxEnqueued.get(), failed));
        });
        return result;
    }
}
