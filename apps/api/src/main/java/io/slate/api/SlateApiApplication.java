package io.slate.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class SlateApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(SlateApiApplication.class, args);
    }
}
