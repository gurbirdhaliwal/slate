package io.slate.api.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.slate.api.security.ApiKeyService;
import io.slate.api.tenancy.TenantContext;
import io.slate.api.web.dto.IngestRunRequest;
import io.slate.api.web.dto.IngestRunResponse;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Ingest pipeline (§5 data flow, steps 1-3): persist the step graph, compute
 * per-step dollar cost, store raw payloads to MinIO, and — in the SAME
 * transaction — enqueue Stage 1 verdict jobs. A run can never be half-enqueued.
 *
 * Success-run sampling happens in the SDK (sample_success_rate); everything
 * that reaches this endpoint with a terminal status gets analyzed.
 */
@Service
public class IngestService {

    private final JdbcTemplate jdbc; // tenant-aware — RLS sees the caller's org
    private final CostCalculator costCalculator;
    private final PayloadStorageService payloadStorage;
    private final ObjectMapper objectMapper;

    public IngestService(
            JdbcTemplate jdbc,
            CostCalculator costCalculator,
            PayloadStorageService payloadStorage,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.costCalculator = costCalculator;
        this.payloadStorage = payloadStorage;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public IngestRunResponse ingestRun(ApiKeyService.ResolvedKey apiKey, IngestRunRequest request) {
        if (apiKey.projectId() == null) {
            throw new IllegalArgumentException(
                    "API key has no project claim; issue a project-scoped key");
        }
        UUID orgId = TenantContext.get();
        validateEdgeReferences(request.steps());

        // Assign server ids up front so parent references can be mapped
        Map<String, UUID> stepIds = new LinkedHashMap<>();
        request.steps().forEach(s -> stepIds.put(s.clientStepId(), UUID.randomUUID()));

        UUID runId = UUID.randomUUID();
        IngestRunRequest.RunDto run = request.run();
        jdbc.update(
                """
                INSERT INTO agent_runs (id, org_id, project_id, agent_id, agent_version, status,
                                        failure_source, step_count, metadata, started_at, ended_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?, ?)
                """,
                runId, orgId, apiKey.projectId(), run.agentId(), run.agentVersion(), run.status(),
                run.failureSource(), request.steps().size(),
                toJson(run.metadata() == null ? Map.of() : run.metadata()),
                Timestamp.from(run.startedAt()),
                run.endedAt() == null ? null : Timestamp.from(run.endedAt()));

        BigDecimal totalCost = BigDecimal.ZERO;
        for (IngestRunRequest.StepDto step : request.steps()) {
            UUID stepId = stepIds.get(step.clientStepId());
            BigDecimal cost =
                    costCalculator.computeUsd(step.model(), step.inputTokens(), step.outputTokens());
            if (cost != null) {
                totalCost = totalCost.add(cost);
            }

            // Full input/output payload goes to MinIO; the row keeps the pointer
            Map<String, Object> payload = new HashMap<>();
            payload.put("input", step.input());
            payload.put("output", step.output());
            String storageKey = payloadStorage.putStepPayload(orgId, runId, stepId, toJson(payload));

            String parentArray = step.parentClientStepIds() == null
                    ? "{}"
                    : step.parentClientStepIds().stream()
                            .map(cid -> stepIds.get(cid).toString())
                            .collect(Collectors.joining(",", "{", "}"));
            jdbc.update(
                    """
                    INSERT INTO agent_steps (id, run_id, org_id, seq, parent_step_ids, step_type,
                                             name, model, input_tokens, output_tokens, cost_usd,
                                             latency_ms, storage_key)
                    VALUES (?, ?, ?, ?, ?::uuid[], ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    stepId, runId, orgId, step.seq(), parentArray, step.stepType(), step.name(),
                    step.model(), step.inputTokens(), step.outputTokens(), cost,
                    step.latencyMs(), storageKey);
        }

        jdbc.update("UPDATE agent_runs SET total_cost_usd = ? WHERE id = ?", totalCost, runId);

        int enqueued = 0;
        if (!"running".equals(run.status())) {
            enqueued = enqueueAnalysis(orgId, runId, stepIds.values());
        }
        return new IngestRunResponse(runId, request.steps().size(), enqueued);
    }

    /** Stage 1 fan-out: one verdict job per step + the run counter that gates Stage 2 (§10). */
    private int enqueueAnalysis(UUID orgId, UUID runId, Iterable<UUID> stepIds) {
        int count = 0;
        for (UUID stepId : stepIds) {
            jdbc.update(
                    """
                    INSERT INTO analysis_jobs (org_id, run_id, step_id, kind)
                    VALUES (?, ?, ?, 'step_verdict')
                    """,
                    orgId, runId, stepId);
            count++;
        }
        jdbc.update(
                """
                INSERT INTO run_analysis_progress (run_id, org_id, total_verdicts, pending_verdicts)
                VALUES (?, ?, ?, ?)
                """,
                runId, orgId, count, count);
        return count;
    }

    /** Every parent must reference a step in this batch, and not the step itself. */
    private void validateEdgeReferences(List<IngestRunRequest.StepDto> steps) {
        Set<String> ids = steps.stream()
                .map(IngestRunRequest.StepDto::clientStepId)
                .collect(Collectors.toSet());
        if (ids.size() != steps.size()) {
            throw new IllegalArgumentException("Duplicate client_step_id in step graph");
        }
        for (IngestRunRequest.StepDto step : steps) {
            if (step.parentClientStepIds() == null) {
                continue;
            }
            for (String parent : step.parentClientStepIds()) {
                if (!ids.contains(parent)) {
                    throw new IllegalArgumentException(
                            "Step '%s' references unknown parent '%s'"
                                    .formatted(step.clientStepId(), parent));
                }
                if (parent.equals(step.clientStepId())) {
                    throw new IllegalArgumentException(
                            "Step '%s' references itself".formatted(step.clientStepId()));
                }
            }
        }
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Unserializable payload", e);
        }
    }
}
