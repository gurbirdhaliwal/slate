package io.slate.api.web.dto;

import java.util.UUID;

public record IngestRunResponse(UUID runId, int accepted, int enqueuedJobs) {}
