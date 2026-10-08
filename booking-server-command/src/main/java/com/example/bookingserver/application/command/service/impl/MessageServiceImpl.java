package com.example.bookingserver.application.command.service.impl;

import com.example.bookingserver.application.command.service.MessageService;
import lombok.RequiredArgsConstructor;
import lombok.SneakyThrows;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;

@Component
@RequiredArgsConstructor
@EnableAsync
public class MessageServiceImpl implements MessageService {

    final JavaMailSender javaMailSender;
    @Value("${mail.user}")
    private String senderEmail;

    @Override
    @SneakyThrows
    @Async
    public void sendMail(String subject, String email, String content, boolean isHtml) {
        var message = javaMailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(message, true);

        helper.setFrom(senderEmail, "Bekoo- Sức khoẻ tận tay");
        helper.setTo(email);

        helper.setSubject(subject);
        helper.setText(content, isHtml);
        javaMailSender.send(message);

    }

    @Override
    public void sendSms(String phoneNumber, String content, boolean isHtml) {

    }
}
