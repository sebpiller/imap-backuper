package ch.sebpiller.mail.internal;

import ch.sebpiller.mail.DownloadResult.DomainStatistic;
import lombok.extern.slf4j.Slf4j;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Walks a finished download tree ({@code <root>/<domain>/.../N/}) and aggregates,
 * per top-level domain directory, the number of mails and the total bytes on disk.
 */
@Slf4j
public final class DomainStatisticsCollector {

    private DomainStatisticsCollector() {
    }

    /**
     * Returns one {@link DomainStatistic} per domain directory directly under
     * {@code root}, sorted by domain name.
     */
    public static List<DomainStatistic> collect(Path root) throws IOException {
        // Map: domain -> [emailCount, totalFolderSize]
        Map<String, long[]> domainStats = new ConcurrentHashMap<>();

        try (var domainStream = Files.walk(root, 1)) {
            domainStream
                    .filter(Files::isDirectory)
                    .filter(path -> !path.equals(root))
                    .forEach(domainPath -> {
                        var domainName = domainPath.getFileName().toString();
                        try {
                            var emailCount = new AtomicInteger(0);
                            var totalSize = new AtomicInteger(0);

                            try (var emailStream = Files.walk(domainPath)) {
                                emailStream
                                        .filter(Files::isDirectory)
                                        .filter(path -> {
                                            // Check if this is a mail directory (numeric name)
                                            var name = path.getFileName().toString();
                                            return name.matches("\\d+");
                                        })
                                        .forEach(mailDir -> {
                                            emailCount.incrementAndGet();
                                            try (var fileStream = Files.walk(mailDir)) {
                                                fileStream
                                                        .filter(Files::isRegularFile)
                                                        .forEach(file -> {
                                                            try {
                                                                totalSize.addAndGet((int) Files.size(file));
                                                            } catch (IOException e) {
                                                                log.warn("Could not get size of file {}: {}", file, e.getMessage());
                                                            }
                                                        });
                                            } catch (IOException e) {
                                                log.warn("Error walking mail directory {}: {}", mailDir, e.getMessage());
                                            }
                                        });
                            }

                            domainStats.put(domainName, new long[]{emailCount.get(), totalSize.get()});
                        } catch (IOException e) {
                            log.warn("Error processing domain directory {}: {}", domainPath, e.getMessage());
                        }
                    });
        }

        List<DomainStatistic> result = new ArrayList<>();
        domainStats.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> result.add(
                        new DomainStatistic(entry.getKey(), entry.getValue()[0], entry.getValue()[1])));
        return result;
    }
}
