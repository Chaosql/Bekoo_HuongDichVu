package com.example.bookingserver.application.command.service.impl;

import java.util.Base64;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.User;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;

class JwtEnvironmentTest {
    @Test
    void configuredSecretSignsAndValidatesTokens() {
        JwtServiceImpl service = new JwtServiceImpl();
        String secret = Base64.getEncoder().encodeToString(new byte[32]);
        ReflectionTestUtils.setField(service, "SECRET_KEY", secret);
        var user = User.withUsername("test-user").password("unused").roles("USER").build();
        String token = service.generateToken(Map.of(), user, 60000L);
        assertEquals("test-user", service.extractUsername(token));
        assertTrue(service.isTokenValid(token, user));
        byte[] otherKey = new byte[32];
        otherKey[0] = 1;
        ReflectionTestUtils.setField(service, "SECRET_KEY", Base64.getEncoder().encodeToString(otherKey));
        assertThrows(io.jsonwebtoken.security.SignatureException.class,
                () -> service.extractUsername(token));
    }
}
