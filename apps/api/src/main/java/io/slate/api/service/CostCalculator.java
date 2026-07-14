package io.slate.api.service;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Per-step dollar cost, computed at ingest from tokens x model price (§9).
 * Cost is a first-class schema property — this feeds the Phase 2/3
 * cost-per-quality expansion, so keep the price table current.
 *
 * Prices are USD per million tokens {input, output}. Longest-prefix match so
 * dated model ids (claude-haiku-4-5-20251001) hit their family row.
 */
@Service
public class CostCalculator {

    private static final Logger log = LoggerFactory.getLogger(CostCalculator.class);

    // Ordered longest-prefix-first within each family
    private static final Map<String, double[]> PRICES_PER_MTOK = new LinkedHashMap<>();

    static {
        PRICES_PER_MTOK.put("claude-haiku", new double[] {0.25, 1.25});
        PRICES_PER_MTOK.put("claude-sonnet", new double[] {3.0, 15.0});
        PRICES_PER_MTOK.put("claude-opus", new double[] {15.0, 75.0});
        PRICES_PER_MTOK.put("gpt-4o-mini", new double[] {0.15, 0.60});
        PRICES_PER_MTOK.put("gpt-4o", new double[] {2.50, 10.0});
        PRICES_PER_MTOK.put("text-embedding-3-small", new double[] {0.02, 0.0});
    }

    /** Returns null when model or tokens are unknown — never guess a price. */
    public BigDecimal computeUsd(String model, Integer inputTokens, Integer outputTokens) {
        if (model == null || (inputTokens == null && outputTokens == null)) {
            return null;
        }
        double[] price = lookup(model);
        if (price == null) {
            log.warn("No price entry for model '{}' — storing null cost", model);
            return null;
        }
        double in = inputTokens == null ? 0 : inputTokens;
        double out = outputTokens == null ? 0 : outputTokens;
        BigDecimal usd = BigDecimal.valueOf(in / 1_000_000.0 * price[0])
                .add(BigDecimal.valueOf(out / 1_000_000.0 * price[1]), MathContext.DECIMAL64);
        return usd.setScale(6, RoundingMode.HALF_UP); // matches NUMERIC(10,6)
    }

    private double[] lookup(String model) {
        String normalized = model.toLowerCase();
        return PRICES_PER_MTOK.entrySet().stream()
                .filter(e -> normalized.startsWith(e.getKey()))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElse(null);
    }
}
