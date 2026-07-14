package io.slate.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "slate")
public record SlateProperties(String apiKeyPepper, Jwt jwt, Minio minio) {

    public record Jwt(String privateKeyPath, long ttlSeconds) {}

    public record Minio(String endpoint, String accessKey, String secretKey, String bucket) {}
}
