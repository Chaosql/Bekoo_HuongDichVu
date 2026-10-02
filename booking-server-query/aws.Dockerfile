FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
RUN addgroup -S spring && adduser -S spring -G spring \
    && mkdir -p /app/logs && chown spring:spring /app/logs
COPY --chown=spring:spring booking-server-query/target/booking-server-query-0.0.1-SNAPSHOT.jar app.jar
USER spring:spring
ENV SPRING_PROFILES_ACTIVE=aws
ENV SERVER_PORT=8081
ENV JAVA_TOOL_OPTIONS="-Xms256m -Xmx768m -XX:+UseG1GC"
EXPOSE 8081
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=8 \
  CMD wget -q -O /dev/null "http://127.0.0.1:${SERVER_PORT}/actuator/health" || exit 1
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
