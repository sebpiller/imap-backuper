package ch.sebpiller.mail;

/**
 * A single IMAP account to browse. Each mailbox is downloaded on its own thread
 * with its own mail session and store connection.
 *
 * <p>Create instances with the fluent {@link #builder()}:
 * <pre>{@code
 * Mailbox box = Mailbox.builder()
 *         .host("imap.gmail.com")
 *         .username("me@gmail.com")
 *         .password("app-password")
 *         .build();   // port defaults to 993
 * }</pre>
 */
public record Mailbox(String host, int port, String username, String password) {

    /** Default IMAP-over-SSL port. */
    public static final int DEFAULT_PORT = 993;

    public Mailbox {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("Mailbox host is required");
        }
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("Mailbox username is required");
        }
        if (password == null) {
            throw new IllegalArgumentException("Mailbox password is required");
        }
        if (port <= 0) {
            throw new IllegalArgumentException("Mailbox port must be positive, was " + port);
        }
    }

    public static Builder builder() {
        return new Builder();
    }

    /** Fluent builder for a {@link Mailbox}; {@code port} defaults to {@link #DEFAULT_PORT}. */
    public static final class Builder {
        private String host;
        private int port = DEFAULT_PORT;
        private String username;
        private String password;

        private Builder() {
        }

        public Builder host(String host) {
            this.host = host;
            return this;
        }

        public Builder port(int port) {
            this.port = port;
            return this;
        }

        public Builder username(String username) {
            this.username = username;
            return this;
        }

        public Builder password(String password) {
            this.password = password;
            return this;
        }

        public Mailbox build() {
            return new Mailbox(host, port, username, password);
        }
    }
}
