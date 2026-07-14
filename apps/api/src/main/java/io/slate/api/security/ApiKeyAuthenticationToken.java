package io.slate.api.security;

import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

/** Authentication for SDK ingest requests; principal is the resolved key (org + project). */
public class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {

    private final ApiKeyService.ResolvedKey key;

    public ApiKeyAuthenticationToken(ApiKeyService.ResolvedKey key) {
        super(List.of(new SimpleGrantedAuthority("ROLE_SDK")));
        this.key = key;
        setAuthenticated(true);
    }

    @Override
    public Object getCredentials() {
        return "";
    }

    @Override
    public Object getPrincipal() {
        return key;
    }
}
