package com.example.bookingserver;

import com.example.bookingserver.application.command.command.user.CreateUserCommand;
import com.example.bookingserver.application.command.handle.user.CreateUserHandler;
import com.example.bookingserver.domain.ERole;
import com.example.bookingserver.domain.Role;
import com.example.bookingserver.infrastructure.persistence.repository.RoleJpaRepository;
import com.example.bookingserver.infrastructure.persistence.repository.UserJpaRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.annotation.Value;

import java.util.HashSet;
import java.util.Set;

@Slf4j
@SpringBootApplication
@RequiredArgsConstructor
public class BookingServerCommandApplication implements ApplicationRunner {

	public static void main(String[] args) {
		SpringApplication.run(BookingServerCommandApplication.class, args);
	}

	final RoleJpaRepository roleJpaRepository;
	final UserJpaRepository userJpaRepository;
	final CreateUserHandler createUserHandler;
	@Value("${ADMIN_EMAIL:}")
	private String adminEmail;
	@Value("${ADMIN_PASSWORD:}")
	private String adminPassword;
	@Value("${ADMIN_NAME:Quản trị hệ thống}")
	private String adminName;
	@Value("${ADMIN_CCCD:}")
	private String adminCccd;
	@Value("${ADMIN_PHONE:}")
	private String adminPhone;
	@Value("${ADMIN_PROVINCE:}")
	private String adminProvince;
	@Value("${ADMIN_DISTRICT:}")
	private String adminDistrict;
	@Value("${ADMIN_COMMUNE:}")
	private String adminCommune;
	@Value("${ADMIN_DOB:}")
	private String adminDob;
	@Value("${ADMIN_GENDER:}")
	private String adminGender;
	@Override
	public void run(ApplicationArguments args){
		if(!roleJpaRepository.existsById(ERole.ADMIN.name())) {
			Role role_admin = new Role(ERole.ADMIN);
			roleJpaRepository.save(role_admin);
		}
		if(!roleJpaRepository.existsById(ERole.DOCTOR.name())) {
			Role role = new Role(ERole.DOCTOR);
			roleJpaRepository.save(role);
		}
		if(!roleJpaRepository.existsById(ERole.USER.name())) {
			Role role = new Role(ERole.USER);
			roleJpaRepository.save(role);
		}
		if (adminEmail.isBlank() && adminPassword.isBlank()) {
			log.info("Admin initialization disabled: no admin credentials configured");
			return;
		}
		if (adminEmail.isBlank() || adminPassword.isBlank()) {
			throw new IllegalStateException("Configure both ADMIN_EMAIL and ADMIN_PASSWORD");
		}
		if(!userJpaRepository.existsByEmail(adminEmail)){
			if (adminCccd.isBlank() || adminPhone.isBlank() || adminProvince.isBlank()
					|| adminDistrict.isBlank() || adminCommune.isBlank()
					|| adminDob.isBlank() || adminGender.isBlank()) {
				throw new IllegalStateException("Configure the required ADMIN_* profile fields");
			}
			CreateUserCommand command = new CreateUserCommand();
			command.setName(adminName);
			command.setCccd(adminCccd);
			command.setEmail(adminEmail);
			command.setPassword(adminPassword);
			command.setConfirmPassword(adminPassword);
			command.setPhoneNumber(adminPhone);
			command.setProvince(adminProvince);
			command.setDistrict(adminDistrict);
			command.setCommune(adminCommune);
			command.setDob(adminDob);
			command.setGender(adminGender);
			Set<Role> roles = new HashSet<>();
			roles.add(new Role(ERole.ADMIN));
			createUserHandler.execute(command, roles);
			log.info("Create ADMIN account successfully");
		}
	}
}
