package io.slate.api.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Unauthenticated — used by Uptime Kuma and the compose healthcheck (§12). */
@RestController
public class HealthController {

    private static final String VERSION = "0.1.0";

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok", "version", VERSION);
    }
}
