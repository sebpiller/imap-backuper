package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.internal.SyncState.Key;
import ch.sebpiller.mail.internal.SyncState.Mark;
import lombok.extern.slf4j.Slf4j;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Reads and writes a {@link SyncState} to a small, human-readable text file used
 * to drive incremental downloads. Each line holds one folder's high-water mark as
 * TAB-separated fields:
 *
 * <pre>{@code
 * # mail-sync-state v1
 * # username<TAB>folderFullName<TAB>uidValidity<TAB>lastUid
 * me@example.com	INBOX	1700000000	9981
 * }</pre>
 *
 * <p>Deleting the file simply makes the next run a full download again.
 */
@Slf4j
public final class SyncStateStore {

    private static final String HEADER = "# mail-sync-state v1\n"
            + "# username\tfolderFullName\tuidValidity\tlastUid\n";

    private SyncStateStore() {
    }

    /**
     * Loads previously persisted marks. A missing file yields an
     * {@linkplain SyncState#empty() empty} state; malformed lines are logged and
     * skipped so a partially corrupt file never aborts a run.
     */
    public static SyncState load(Path file) {
        if (file == null || !Files.exists(file)) {
            return SyncState.empty();
        }
        Map<Key, Mark> marks = new LinkedHashMap<>();
        try {
            for (var line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
                if (line.isBlank() || line.startsWith("#")) {
                    continue;
                }
                var fields = line.split("\t", -1);
                if (fields.length != 4) {
                    log.warn("Ignoring malformed sync-state line (expected 4 fields): {}", line);
                    continue;
                }
                try {
                    var key = new Key(fields[0], fields[1]);
                    var mark = new Mark(Long.parseLong(fields[2]), Long.parseLong(fields[3]));
                    marks.put(key, mark);
                } catch (NumberFormatException e) {
                    log.warn("Ignoring sync-state line with non-numeric uid/validity: {}", line);
                }
            }
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to read sync-state file " + file, e);
        }
        log.info("Loaded {} folder mark(s) from sync-state file {}", marks.size(), file);
        return new SyncState(marks);
    }

    /**
     * Persists the state's {@linkplain SyncState#snapshot() snapshot}, creating
     * parent directories if needed. The file is rewritten in full on each save.
     */
    public static void save(Path file, SyncState state) {
        var snapshot = state.snapshot();
        var sb = new StringBuilder(HEADER);
        // Stable ordering keeps diffs of the file readable across runs.
        List<Map.Entry<Key, Mark>> entries = new ArrayList<>(snapshot.entrySet());
        entries.sort((a, b) -> {
            var byUser = a.getKey().username().compareTo(b.getKey().username());
            return byUser != 0 ? byUser : a.getKey().folderFullName().compareTo(b.getKey().folderFullName());
        });
        for (var entry : entries) {
            sb.append(entry.getKey().username()).append('\t')
                    .append(entry.getKey().folderFullName()).append('\t')
                    .append(entry.getValue().uidValidity()).append('\t')
                    .append(entry.getValue().lastUid()).append('\n');
        }
        try {
            if (file.getParent() != null) {
                Files.createDirectories(file.getParent());
            }
            Files.writeString(file, sb.toString(), StandardCharsets.UTF_8);
            log.info("Saved {} folder mark(s) to sync-state file {}", snapshot.size(), file);
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to write sync-state file " + file, e);
        }
    }
}
