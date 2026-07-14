package io.slate.api.tenancy;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DelegatingDataSource;

/**
 * HAND-CODED (§9/§13). Stamps app.current_org_id on every connection handed to
 * application code, so RLS policies see the tenant. Fails closed: no org on the
 * thread means no connection at all.
 *
 * Pool-reset (§9 warning): set_config(..., false) persists on the pooled
 * connection after release, so close() is intercepted to RESET the setting
 * before the connection returns to the pool. A stale org_id on a pooled
 * connection is a cross-tenant data leak.
 */
public class TenantAwareDataSource extends DelegatingDataSource {

    public TenantAwareDataSource(DataSource targetDataSource) {
        super(targetDataSource);
    }

    @Override
    public Connection getConnection() throws SQLException {
        Connection conn = super.getConnection();
        UUID orgId = TenantContext.get();
        if (orgId == null) { // no request without an org may touch tenant tables
            conn.close();
            throw new IllegalStateException("No org context on this thread");
        }
        try (PreparedStatement ps =
                conn.prepareStatement("SELECT set_config('app.current_org_id', ?, false)")) {
            ps.setString(1, orgId.toString());
            ps.execute();
        } catch (SQLException e) {
            conn.close();
            throw e;
        }
        return withResetOnClose(conn);
    }

    @Override
    public Connection getConnection(String username, String password) throws SQLException {
        throw new UnsupportedOperationException(
                "Per-credential connections bypass tenant stamping; use getConnection()");
    }

    private Connection withResetOnClose(Connection delegate) {
        return (Connection) Proxy.newProxyInstance(
                getClass().getClassLoader(),
                new Class<?>[] {Connection.class},
                (proxy, method, args) -> {
                    if ("close".equals(method.getName()) && !delegate.isClosed()) {
                        try (Statement st = delegate.createStatement()) {
                            st.execute("RESET app.current_org_id");
                        }
                    }
                    try {
                        return method.invoke(delegate, args);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });
    }
}
