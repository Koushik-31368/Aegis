package com.aegis.edge;

import ai.onnxruntime.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.nio.FloatBuffer;
import java.util.Collections;
import java.util.Map;

/**
 * Loads model.onnx (trained in ai-training/train_model.py) and scores each
 * reading's criticality.
 *
 * IMPORTANT: this class is deliberately self-contained and easy to test on
 * its own BEFORE it's wired into the live TelemetryController. If ONNX
 * loading is going to fail, you want to find out from a quick standalone
 * test, not from a confusing error buried in the middle of a live request.
 */
@Component
public class CriticalityScorer {

    private static final Logger log = LoggerFactory.getLogger(CriticalityScorer.class);

    private OrtEnvironment env;
    private OrtSession session;

    // Isolation Forest "scores" output: roughly in the range [-0.15, +0.15]
    // in our training run (see train_model.py sanity check). Positive =
    // normal, negative = anomalous. We map that to a 1-10 criticality scale
    // where 10 = most critical. These bounds came directly from the sanity
    // check output when the model was trained - if you retrain with
    // different data, re-check these bounds.
    private static final float SCORE_MOST_NORMAL = 0.12f;
    private static final float SCORE_MOST_CRITICAL = -0.15f;

    public CriticalityScorer() {
        try {
            env = OrtEnvironment.getEnvironment();
            // Loads model.onnx from src/main/resources - Spring puts resources
            // on the classpath, so this path works both from an IDE and from
            // the packaged jar.
            var modelStream = getClass().getClassLoader().getResourceAsStream("model.onnx");
            if (modelStream == null) {
                throw new IllegalStateException(
                        "model.onnx not found on classpath. Did you copy it into "
                                + "edge-gateway/src/main/resources/ ?");
            }
            byte[] modelBytes = modelStream.readAllBytes();
            session = env.createSession(modelBytes, new OrtSession.SessionOptions());
            log.info("Loaded ONNX criticality model. Inputs: {}, Outputs: {}",
                    session.getInputNames(), session.getOutputNames());
        } catch (Exception e) {
            throw new RuntimeException("Failed to load ONNX model", e);
        }
    }

    /**
     * Scores a single reading's value and returns a criticality score from
     * 1 (completely normal) to 10 (highly critical/anomalous).
     */
    public int scoreCriticality(double value) {
        try {
            float[] input = new float[]{(float) value};
            long[] shape = new long[]{1, 1};

            try (OnnxTensor inputTensor = OnnxTensor.createTensor(
                    env, FloatBuffer.wrap(input), shape)) {

                Map<String, OnnxTensor> inputs = Collections.singletonMap(
                        session.getInputNames().iterator().next(), inputTensor);

                try (OrtSession.Result result = session.run(inputs)) {
                    // Second output is "scores" (continuous). First is "label" (1/-1).
                    // We use the continuous score for a graded 1-10 scale instead of
                    // a binary flag - this is what lets the eviction logic in Phase 3
                    // rank readings against each other instead of just yes/no.
                    float[][] scoresOutput = (float[][]) result.get(1).getValue();
                    float rawScore = scoresOutput[0][0];
                    return mapToCriticality(rawScore);
                }
            }
        } catch (OrtException e) {
            log.error("ONNX inference failed for value={}, defaulting to mid criticality", value, e);
            return 5; // fail safe: treat as medium priority rather than crash the request
        }
    }

    private int mapToCriticality(float rawScore) {
        // Clamp and linearly map [SCORE_MOST_CRITICAL, SCORE_MOST_NORMAL] -> [10, 1]
        float clamped = Math.max(SCORE_MOST_CRITICAL, Math.min(SCORE_MOST_NORMAL, rawScore));
        float normalized = (clamped - SCORE_MOST_CRITICAL) / (SCORE_MOST_NORMAL - SCORE_MOST_CRITICAL);
        int criticality = Math.round(10 - (normalized * 9)); // 1 = most normal, 10 = most critical
        return Math.max(1, Math.min(10, criticality));
    }
}
