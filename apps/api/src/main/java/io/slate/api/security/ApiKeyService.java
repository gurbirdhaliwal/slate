package io.slate.api.security;

import io.slate.api.config.SlateProperties;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * HAND-CODED (§13): API key hashing + resolution. Keys are stored as
 * SHA-256(key || server pepper) — never plaintext. Uses the RAW datasource:
 * this lookup happens before any org context exists.
 */
@Service
public class ApiKeyService {

    /** Org + optional project claim resolved from a presented API key. */
    public record ResolvedKey(UUID keyId, UUID orgId, UUID projectId) {}

    private final JdbcTemplate rawJdbc;
    private final String pepper;

    public ApiKeyService(@Qualifier("rawJdbcTemplate") JdbcTemplate rawJdbc, SlateProperties props) {
        this.rawJdbc = rawJdbc;
        this.pepper = props.apiKeyPepper();
    }

    public Optional<ResolvedKey> resolve(String presentedKey) {
        String hash = sha256Hex(presentedKey + pepper);
        List<ResolvedKey> matches = rawJdbc.query(
                "SELECT id, org_id, project_id FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
                (rs, i) -> new ResolvedKey(
                        rs.getObject("id", UUID.class),
                        rs.getObject("org_id", UUID.class),
                        rs.getObject("project_id", UUID.class)),
                hash);
        return matches.stream().findFirst();
    }

    // TODO(Phase 1): issueKey(orgId, projectId, name) — generate `sk_slate_` + 32 random
    // bytes, store hash + prefix, return plaintext exactly once (dashboard key issuance).

    static String sha256Hex(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(input.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
