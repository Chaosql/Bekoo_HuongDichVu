package com.example.bookingserverquery.infrastructure.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenAPIConfig {

    @Value("${spring.url}")
    private String springUrl;

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Bekoo_HuongDichVu - Query API")
                        .version("1.0")
                        .description("RestApi for front-end developer")
                        .contact(new Contact()
                                .name("Chaosql")
                                .url("https://github.com/Chaosql/Bekoo_HuongDichVu"))
                )
                .addServersItem(new Server()
                        .url(springUrl)
                        .description("Bekoo_HuongDichVu Query"))
                ;
    }

}
