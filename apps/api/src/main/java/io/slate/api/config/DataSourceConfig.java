package io.slate.api.config;

import com.zaxxer.hikari.HikariDataSource;
import io.slate.api.tenancy.TenantAwareDataSource;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.flyway.FlywayDataSource;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Two views of the same Postgres:
 *  - "raw"  — used by Flyway (no org context at boot) and by pre-auth lookups
 *             against non-RLS tables (api_keys, users, organizations)
 *  - primary (tenant-aware) — everything else; stamps app.current_org_id so
 *             RLS enforces org isolation on every query
 */
@Configuration
public class DataSourceConfig {

    @Bean
    @ConfigurationProperties("spring.datasource")
    DataSourceProperties dataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @FlywayDataSource
    DataSource rawDataSource(DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder().type(HikariDataSource.class).build();
    }

    @Bean
    @Primary
    DataSource tenantAwareDataSource(@Qualifier("rawDataSource") DataSource raw) {
        return new TenantAwareDataSource(raw);
    }

    /** Pre-tenant lookups ONLY (auth tables carry no RLS). */
    @Bean
    JdbcTemplate rawJdbcTemplate(@Qualifier("rawDataSource") DataSource raw) {
        return new JdbcTemplate(raw);
    }

    @Bean
    @Primary
    JdbcTemplate tenantJdbcTemplate(@Qualifier("tenantAwareDataSource") DataSource tenantAware) {
        return new JdbcTemplate(tenantAware);
    }
}
