package com.example.bookingserver.application.command.service.impl;

import com.example.bookingserver.controller.GenerateData;
import com.example.bookingserver.domain.repository.UserRepository;
import com.example.bookingserver.infrastructure.persistence.repository.ChatBotJpaRepository;
import com.example.bookingserver.infrastructure.persistence.repository.RedisRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AiFeatureDisabledTest {
    private final ApplicationContextRunner context = new ApplicationContextRunner()
            .withUserConfiguration(GPTServiceImpl.class, GenerateData.class);

    @Test
    void missingAiSettingsDoNotRegisterGptOrItsEndpoint() {
        context.run(ctx -> {
            assertNull(ctx.getStartupFailure());
            assertTrue(ctx.getBeansOfType(GPTServiceImpl.class).isEmpty());
            assertTrue(ctx.getBeansOfType(GenerateData.class).isEmpty());
        });
    }

    @Test
    void explicitlyDisabledAiDoesNotRequireCredentials() {
        context.withPropertyValues("features.ai.enabled=false").run(ctx -> {
            assertNull(ctx.getStartupFailure());
            assertTrue(ctx.getBeansOfType(GPTServiceImpl.class).isEmpty());
            assertTrue(ctx.getBeansOfType(GenerateData.class).isEmpty());
        });
    }

    @Test
    void chatSkipsAiRequestWhenDisabledEvenWithInvalidEndpoint() {
        var users = mock(UserRepository.class);
        var messages = mock(ChatBotJpaRepository.class);
        var redis = mock(RedisRepository.class);
        when(users.findById("visitor")).thenReturn(Optional.empty());
        var service = new ChatBotServiceImpl(messages, users, new ObjectMapper(), redis);
        ReflectionTestUtils.setField(service, "URL", "invalid-endpoint");
        ReflectionTestUtils.setField(service, "aiEnabled", false);
        assertEquals("", service.chat(null, Map.of("senderId", "visitor", "content", "hello")));
        verifyNoInteractions(messages, redis);
    }
}
