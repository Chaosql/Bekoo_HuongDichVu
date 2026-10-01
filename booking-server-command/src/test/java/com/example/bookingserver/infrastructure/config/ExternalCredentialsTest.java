package com.example.bookingserver.infrastructure.config;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;

class ExternalCredentialsTest {
    @Test
    void cloudinaryUsesInjectedCredentials() {
        CloudinaryConfig config = new CloudinaryConfig();
        ReflectionTestUtils.setField(config, "CLOUD_NAME", "test-cloud");
        ReflectionTestUtils.setField(config, "API_KEY", "test-api-key");
        ReflectionTestUtils.setField(config, "API_SECRET", "test-api-secret");
        var client = config.cloudinary();
        assertEquals("test-cloud", client.config.cloudName);
        assertEquals("test-api-key", client.config.apiKey);
        assertEquals("test-api-secret", client.config.apiSecret);
    }

    @Test
    void vnPaySigningUsesConfiguredKey() {
        VNPayConfig config = new VNPayConfig();
        config.secretKey = "test-signing-key";
        Map<String, String> fields = Map.of("b", "two", "a", "one");
        String expected = VNPayConfig.hmacSHA512("test-signing-key", "a=one&b=two");
        assertFalse(expected.isEmpty());
        assertEquals(expected, config.hashAllFields(fields));
        config.secretKey = "different-test-key";
        assertNotEquals(expected, config.hashAllFields(fields));
    }
}
