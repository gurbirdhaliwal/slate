package io.slate.api.config;

import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

/**
 * Standard S3 client pointed at MinIO (§7) — swapping to S3/R2 later is a
 * config change, not a code change. Path-style access is required by MinIO.
 */
@Configuration
public class MinioConfig {

    @Bean
    S3Client s3Client(SlateProperties props) {
        return S3Client.builder()
                .endpointOverride(URI.create(props.minio().endpoint()))
                .region(Region.US_EAST_1) // ignored by MinIO, required by the SDK
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(
                                props.minio().accessKey(), props.minio().secretKey())))
                .serviceConfiguration(
                        S3Configuration.builder().pathStyleAccessEnabled(true).build())
                .build();
    }
}
