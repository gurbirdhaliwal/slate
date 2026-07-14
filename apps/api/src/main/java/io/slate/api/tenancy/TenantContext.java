package io.slate.api.tenancy;

import java.util.UUID;

/**
 * HAND-CODED (§9/§13). Holds the authenticated org for the current request thread.
 * Set by the auth filter after resolving the API key or JWT; read by
 * {@link TenantAwareDataSource} to stamp app.current_org_id on every connection
 * the request uses (which RLS policies then enforce).
 *
 * clear() MUST run in a finally block per request — a leaked org on a pooled
 * thread is a cross-tenant data leak.
 */
public final class TenantContext {

    private static final ThreadLocal<UUID> ORG = new ThreadLocal<>();

    private TenantContext() {}

    public static void set(UUID orgId) {
        ORG.set(orgId);
    }

    public static UUID get() {
        return ORG.get();
    }

    public static void clear() {
        ORG.remove();
    }
}
