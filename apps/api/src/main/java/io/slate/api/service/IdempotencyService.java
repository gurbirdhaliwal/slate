package io.slate.api.service;

import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * HAND-CODED (§12/§13): duplicate runs or double-billing are hard to debug in
 * production. INSERT ... ON CONFLICT DO NOTHING makes check-and-claim atomic;
 * the response must be written back in the SAME transaction that creates the
 * resource. Used by run creation + CI webhook when those land (Phase 3);
 * the table exists from day one.
 */
@Service
public class IdempotencyService {

    private final JdbcTemplate rawJdbc; // idempotency_keys carries no RLS

    public IdempotencyService(@Qualifier("rawJdbcTemplate") JdbcTemplate rawJdbc) {
        this.rawJdbc = rawJdbc;
    }

    /** True if this call claimed the key (caller proceeds); false if it already existed. */
    public boolean claim(UUID orgId, String key) {
        int inserted = rawJdbc.update(
                "INSERT INTO idempotency_keys (org_id, key) VALUES (?, ?) ON CONFLICT DO NOTHING",
                orgId, key);
        return inserted == 1;
    }

    /** Stored response for a previously completed request; empty while first request in flight. */
    public Optional<String> storedResponse(UUID orgId, String key) {
        return rawJdbc.query(
                        "SELECT response::text FROM idempotency_keys WHERE org_id = ? AND key = ?",
                        (rs, i) -> rs.getString(1), orgId, key)
                .stream()
                .filter(java.util.Objects::nonNull)
                .findFirst();
    }

    /** Call inside the same transaction that created the resource. */
    public void storeResponse(UUID orgId, String key, String responseJson) {
        rawJdbc.update(
                "UPDATE idempotency_keys SET response = ?::jsonb WHERE org_id = ? AND key = ?",
                responseJson, orgId, key);
    }
}
