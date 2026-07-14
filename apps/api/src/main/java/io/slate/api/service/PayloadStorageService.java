package io.slate.api.service;

import io.slate.api.config.SlateProperties;
import java.util.UUID;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * Raw step payloads live in MinIO, not Postgres (§7):
 *   slate-payloads/{org_id}/runs/{run_id}/{step_id}.json
 * The DB row keeps only the storage_key pointer.
 */
@Service
public class PayloadStorageService {

    private final S3Client s3;
    private final String bucket;

    public PayloadStorageService(S3Client s3, SlateProperties props) {
        this.s3 = s3;
        this.bucket = props.minio().bucket();
    }

    /** Returns the storage key written to agent_steps.storage_key. */
    public String putStepPayload(UUID orgId, UUID runId, UUID stepId, String payloadJson) {
        String key = "%s/runs/%s/%s.json".formatted(orgId, runId, stepId);
        s3.putObject(
                PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .contentType("application/json")
                        .build(),
                RequestBody.fromString(payloadJson));
        return key;
    }
}
