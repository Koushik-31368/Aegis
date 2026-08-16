package com.aegis.edge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootApplication
public class EdgeGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(EdgeGatewayApplication.class, args);
    }

    // WebClient used to forward telemetry to the cloud aggregator.
    // Base URL is read from application.yml (cloud.aggregator.url).
    @Bean
    public WebClient cloudWebClient(
            org.springframework.core.env.Environment env) {
        String cloudUrl = env.getProperty("cloud.aggregator.url", "http://localhost:8081");
        return WebClient.builder().baseUrl(cloudUrl).build();
    }
}
