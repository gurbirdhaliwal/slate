package io.slate.api.web.dto;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/** GET /v1/runs/{run_id}/diagnosis — the product's core output (§5, §12). */
public record DiagnosisResponse(
        UUID runId,
        UUID originStepId,
        List<UUID> propagatedStepIds,
        String failureClass,
        String evidence,
        String explanation,
        String method, // 'deterministic' | 'escalated'
        String escalationModel,
        BigDecimal wastedCostUsd,
        Boolean confirmedByUser,
        OffsetDateTime createdAt) {}
