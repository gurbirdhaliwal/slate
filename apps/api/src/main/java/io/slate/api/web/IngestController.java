package io.slate.api.web;

import io.slate.api.security.ApiKeyService;
import io.slate.api.service.IngestService;
import io.slate.api.web.dto.IngestRunRequest;
import io.slate.api.web.dto.IngestRunResponse;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/ingest")
public class IngestController {

    private final IngestService ingestService;

    public IngestController(IngestService ingestService) {
        this.ingestService = ingestService;
    }

    /** SDK-facing: batched step graph for one agent run. Rate limit (1000/min/org): TODO. */
    @PostMapping("/runs")
    public ResponseEntity<IngestRunResponse> ingestRun(
            @Valid @RequestBody IngestRunRequest request,
            @AuthenticationPrincipal ApiKeyService.ResolvedKey apiKey) {
        return ResponseEntity.accepted().body(ingestService.ingestRun(apiKey, request));
    }
}
