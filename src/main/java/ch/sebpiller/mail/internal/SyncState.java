package ch.sebpiller.mail.internal;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Thread-safe per-run state backing incremental downloads. For every folder it
 * remembers, keyed by {@code (username, folderFullName)}, the highest IMAP UID
 * that has been processed - the <em>high-water mark</em> - together with the
 * folder's {@code UIDVALIDITY} at the time the mark was taken.
 *
 * <p>A run starts from the marks {@linkplain SyncStateStore#load(java.nio.file.Path)
 * loaded} from the previous run. While the run proceeds:
 * <ul>
 *   <li>the producer calls {@link #resumeAfterUid} to learn the UID to resume
 *       after (only when the folder's current {@code UIDVALIDITY} still matches
 *       the stored one), then {@link #beginFolder} once before enqueuing, and
 *       {@link #recordEnqueued} for each message it enqueues;</li>
 *   <li>a consumer calls {@link #recordFailure} when it fails to write a message.</li>
 * </ul>
 *
 * <p>{@link #snapshot()} then derives the next mark per folder. Because the
 * producer enqueues a <strong>contiguous</strong> UID range starting at
 * {@code carriedLastUid + 1}, the new mark is capped at {@code minFailedUid - 1}
 * so that a message which failed this run is fetched again next run rather than
 * being silently skipped forever.
 */
public final class SyncState {

    /** Identifies a folder within a mailbox. */
    public record Key(String username, String folderFullName) {
    }

    /** A persisted high-water mark: the folder's {@code UIDVALIDITY} and last processed UID. */
    public record Mark(long uidValidity, long lastUid) {
    }

    /** Live, mutable tracking for a folder being processed during the current run. */
    private static final class FolderProgress {
        private final long uidValidity;
        private final AtomicLong maxEnqueued;
        private final AtomicLong minFailedUid = new AtomicLong(Long.MAX_VALUE);

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
        if (mark != null && mark.uidValidity() == currentValidity) {
            return mark.lastUid();
        }
        return 0L;
    }

    /** Initializes live tracking for a folder before any message of it is enqueued. */
    public void beginFolder(String username, String folderFullName, long uidValidity, long carriedLastUid) {
        current.put(new Key(username, folderFullName), new FolderProgress(uidValidity, carriedLastUid));
    }

    /** Records that a message with {@code uid} was enqueued for processing (atomic max). */
    public void recordEnqueued(String username, String folderFullName, long uid) {
        var progress = current.get(new Key(username, folderFullName));
        if (progress != null) {
            progress.maxEnqueued.accumulateAndGet(uid, Math::max);
        }
    }

    /** Records that processing a message with {@code uid} failed (atomic min). */
    public void recordFailure(String username, String folderFullName, long uid) {
        var progress = current.get(new Key(username, folderFullName));
        if (progress != null) {
            progress.minFailedUid.accumulateAndGet(uid, Math::min);
        }
    }

    /**
     * Builds the marks to persist for the next run: every folder carried over from
     * the previous run, overlaid with an advanced mark for each folder visited this
     * run. The advanced UID is {@code maxEnqueued} when nothing failed, otherwise
     * {@code min(maxEnqueued, minFailedUid - 1)} so failed messages are retried.
     */
    public Map<Key, Mark> snapshot() {
        Map<Key, Mark> result = new ConcurrentHashMap<>(previous);
        current.forEach((key, progress) -> {
            var minFailed = progress.minFailedUid.get();
            var newLastUid = minFailed == Long.MAX_VALUE
                    ? progress.maxEnqueued.get()
                    : Math.min(progress.maxEnqueued.get(), minFailed - 1);
            result.put(key, new Mark(progress.uidValidity, newLastUid));
        });
        return result;
    }
}
