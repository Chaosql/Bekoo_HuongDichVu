package com.example.bookingserver;

import com.example.bookingserver.application.command.handle.user.CreateUserHandler;
import com.example.bookingserver.infrastructure.persistence.repository.RoleJpaRepository;
import com.example.bookingserver.infrastructure.persistence.repository.UserJpaRepository;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AdminEnvironmentTest {
    @Test
    void emptyCredentialsDoNotCreateAnAdmin() {
        var roles = mock(RoleJpaRepository.class);
        var users = mock(UserJpaRepository.class);
        var handler = mock(CreateUserHandler.class);
        var app = new BookingServerCommandApplication(roles, users, handler);
        ReflectionTestUtils.setField(app, "adminEmail", "");
        ReflectionTestUtils.setField(app, "adminPassword", "");
        app.run(null);
        verifyNoInteractions(users, handler);
    }

    @Test
    void partialCredentialsFailInsteadOfUsingADefaultPassword() {
        var app = new BookingServerCommandApplication(mock(RoleJpaRepository.class),
                mock(UserJpaRepository.class), mock(CreateUserHandler.class));
        ReflectionTestUtils.setField(app, "adminEmail", "admin@example.test");
        ReflectionTestUtils.setField(app, "adminPassword", "");
        assertThrows(IllegalStateException.class, () -> app.run(null));
    }
}
