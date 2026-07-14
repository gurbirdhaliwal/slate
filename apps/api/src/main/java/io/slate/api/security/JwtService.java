package io.slate.api.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jws;
import io.jsonwebtoken.Jwts;
import io.slate.api.config.SlateProperties;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.interfaces.RSAPrivateCrtKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.RSAPublicKeySpec;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * RS256 dashboard session tokens (§6). The signing key is a PKCS#8 PEM on disk
 * (JWT_PRIVATE_KEY_PATH); generate with:
 *   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out jwt-rs256.pem
 * The public key is derived from the private key's CRT parameters.
 */
@Service
public class JwtService {

    private static final Logger log = LoggerFactory.getLogger(JwtService.class);

    private final PrivateKey privateKey; // null when unconfigured (SDK-only deployments)
    private final PublicKey publicKey;
    private final Duration ttl;

    public JwtService(SlateProperties props) {
        this.ttl = Duration.ofSeconds(props.jwt().ttlSeconds());
        String path = props.jwt().privateKeyPath();
        if (path == null || path.isBlank()) {
            log.warn("JWT_PRIVATE_KEY_PATH not set — dashboard sessions disabled");
            this.privateKey = null;
            this.publicKey = null;
            return;
        }
        try {
            String pem = Files.readString(Path.of(path))
                    .replace("-----BEGIN PRIVATE KEY-----", "")
                    .replace("-----END PRIVATE KEY-----", "")
                    .replaceAll("\\s", "");
            KeyFactory keyFactory = KeyFactory.getInstance("RSA");
            PrivateKey key = keyFactory.generatePrivate(
                    new PKCS8EncodedKeySpec(Base64.getDecoder().decode(pem)));
            if (!(key instanceof RSAPrivateCrtKey crtKey)) {
                throw new IllegalStateException("JWT key must be an RSA CRT private key");
            }
            this.privateKey = key;
            this.publicKey = keyFactory.generatePublic(
                    new RSAPublicKeySpec(crtKey.getModulus(), crtKey.getPublicExponent()));
        } catch (Exception e) {
            // boot-fails-loudly: a misconfigured signing key must not go unnoticed
            throw new IllegalStateException("Failed to load JWT signing key from " + path, e);
        }
    }

    public String issueSession(UUID userId, UUID orgId) {
        requireConfigured();
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(userId.toString())
                .claim("org_id", orgId.toString())
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(ttl)))
                .signWith(privateKey, Jwts.SIG.RS256)
                .compact();
    }

    public Jws<Claims> verify(String token) {
        requireConfigured();
        return Jwts.parser().verifyWith(publicKey).build().parseSignedClaims(token);
    }

    private void requireConfigured() {
        if (privateKey == null) {
            throw new IllegalStateException("JWT signing not configured (JWT_PRIVATE_KEY_PATH)");
        }
    }
}
