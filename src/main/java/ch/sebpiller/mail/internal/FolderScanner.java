package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.filter.FolderExclusion;
import ch.sebpiller.mail.filter.FolderInfo;
import lombok.extern.slf4j.Slf4j;

import javax.mail.Folder;
import javax.mail.MessagingException;
import java.util.ArrayList;
import java.util.List;

/**
 * Walks an IMAP folder tree and lists the message-holding folders that survive
 * the configured {@link FolderExclusion} strategies.
 */
@Slf4j
public final class FolderScanner {

    private final List<FolderExclusion> exclusions;

    public FolderScanner(List<FolderExclusion> exclusions) {
        this.exclusions = List.copyOf(exclusions);
    }

    /**
     * Returns the full names of every folder reachable from {@code root} that can
     * hold messages and is not filtered out by any configured exclusion.
     */
    public List<String> collectMessageFolderNames(Folder root) throws MessagingException {
        List<String> names = new ArrayList<>();
        collect(root, 0, names);
        return names;
    }

    /**
     * Recursively walks the folder tree (without opening folders) and collects the
     * full names of every folder that can hold messages and is not filtered out by
     * any configured {@link FolderExclusion}. The {@code level} is the folder's
     * hierarchy depth; the default (root) folder is level 0, so top-level folders
     * are level 1.
     */
    private void collect(Folder folder, int level, List<String> names) throws MessagingException {
        var fullName = folder.getFullName();
        if ((folder.getType() & Folder.HOLDS_MESSAGES) != 0 && !fullName.isEmpty()) {
            var info = new FolderInfo(fullName, folder.getName(), level);
            var exclusion = firstMatchingExclusion(info);
            if (exclusion != null) {
                log.info("Skipping folder '{}' (level {}): excluded by [{}]", fullName, level, exclusion.description());
            } else {
                names.add(fullName);
            }
        }
        if ((folder.getType() & Folder.HOLDS_FOLDERS) != 0) {
            for (var subfolder : folder.list()) {
                collect(subfolder, level + 1, names);
            }
        }
    }

    /**
     * Returns the first configured exclusion strategy that matches the folder,
     * or {@code null} when the folder should be processed.
     */
    private FolderExclusion firstMatchingExclusion(FolderInfo info) {
        for (var exclusion : exclusions) {
            if (exclusion.excludes(info)) {
                return exclusion;
            }
        }
        return null;
    }
}
