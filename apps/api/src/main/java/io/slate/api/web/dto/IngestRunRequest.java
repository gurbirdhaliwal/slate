package io.slate.api.web.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * POST /v1/ingest/runs body — a complete step graph for one agent run (§12).
 * Bean Validation covers shape; edge-reference integrity (parents point at real
 * client_step_ids) is checked in IngestService.
 */
public record IngestRunRequest(
        @NotNull @Valid RunDto run,
        @NotEmpty @Valid List<StepDto> steps) {

    public record RunDto(
            @NotBlank String agentId,
            String agentVersion,
            @NotBlank @Pattern(regexp = "running|succeeded|failed") String status,
            @Pattern(regexp = "explicit|exception|output_check") String failureSource,
            @NotNull Instant startedAt,
            Instant endedAt,
            Map<String, Object> metadata) {}

    public record StepDto(
            @NotBlank String clientStepId,
            @NotNull @PositiveOrZero Integer seq,
            List<String> parentClientStepIds,
            @NotBlank @Pattern(regexp = "llm|tool|retrieval|handoff") String stepType,
            @NotBlank String name,
            String model,
            @PositiveOrZero Integer inputTokens,
            @PositiveOrZero Integer outputTokens,
            @PositiveOrZero Integer latencyMs,
            Object input,
            Object output) {}
}
