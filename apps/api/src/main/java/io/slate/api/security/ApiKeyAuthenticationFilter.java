package io.slate.api.security;

import io.slate.api.tenancy.TenantContext;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Optional;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * HAND-CODED (§13): the SDK ingest auth path. Resolves the hashed API key,
 * stashes the org in TenantContext (which the tenant-aware DataSource stamps
 * onto every connection for RLS), and — critically — clears it in a finally
 * block so the pooled thread never carries a stale org.
 */
public class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

    private final ApiKeyService apiKeyService;

    public ApiKeyAuthenticationFilter(ApiKeyService apiKeyService) {
        this.apiKeyService = apiKeyService;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header == null || !header.startsWith("Bearer ")) {
            chain.doFilter(request, response); // no credentials — the chain's authz rules reject
            return;
        }

        Optional<ApiKeyService.ResolvedKey> resolved =
                apiKeyService.resolve(header.substring("Bearer ".length()).trim());
        if (resolved.isEmpty()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Invalid API key");
            return;
        }

        try {
            TenantContext.set(resolved.get().orgId());
            SecurityContextHolder.getContext()
                    .setAuthentication(new ApiKeyAuthenticationToken(resolved.get()));
            chain.doFilter(request, response);
        } finally {
            TenantContext.clear(); // MUST run — thread returns to the pool
            SecurityContextHolder.clearContext();
        }
    }
}
