# Multi-stage: build with Maven, run on a slim JRE
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S slate && adduser -S slate -G slate
WORKDIR /app
COPY --from=build /build/target/slate-api-*.jar app.jar
USER slate
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
