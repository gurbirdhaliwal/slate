package io.slate.api.web;

import io.slate.api.web.dto.DiagnosisResponse;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** Uses the tenant-aware (primary) JdbcTemplate — RLS scopes every query to the caller's org. */
@RestController
public class DiagnosisController {

    private final JdbcTemplate jdbc;

    public DiagnosisController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/v1/runs/{runId}/diagnosis")
    public ResponseEntity<?> getDiagnosis(@PathVariable UUID runId) {
        List<DiagnosisResponse> found = jdbc.query(
                """
                SELECT run_id, origin_step_id, propagated_step_ids, failure_class, evidence,
                       explanation, method, escalation_model, wasted_cost_usd,
                       confirmed_by_user, created_at
                FROM diagnoses WHERE run_id = ?
                """,
                (rs, i) -> {
                    UUID[] propagated = (UUID[]) rs.getArray("propagated_step_ids").getArray();
                    return new DiagnosisResponse(
                            rs.getObject("run_id", UUID.class),
                            rs.getObject("origin_step_id", UUID.class),
                            Arrays.asList(propagated),
                            rs.getString("failure_class"),
                            rs.getString("evidence"),
                            rs.getString("explanation"),
                            rs.getString("method"),
                            rs.getString("escalation_model"),
                            rs.getBigDecimal("wasted_cost_usd"),
                            rs.getObject("confirmed_by_user", Boolean.class),
                            rs.getObject("created_at", OffsetDateTime.class));
                },
                runId);
        if (!found.isEmpty()) {
            return ResponseEntity.ok(found.getFirst());
        }

        // Distinguish "still analyzing" from "unknown run"
        Integer runExists = jdbc.queryForObject(
                "SELECT count(*) FROM agent_runs WHERE id = ?", Integer.class, runId);
        if (runExists != null && runExists > 0) {
            return ResponseEntity.status(HttpStatus.ACCEPTED)
                    .body(Map.of("run_id", runId, "status", "analyzing"));
        }
        return ResponseEntity.notFound().build();
    }
}
