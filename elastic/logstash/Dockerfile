# syntax=docker/dockerfile:1.7
# Logstash with the MariaDB JDBC driver and this project's pipelines baked in.
FROM logstash:9.5.3

# MariaDB Connector/J, checked against the checksum Maven Central publishes.
ADD --chown=logstash:root \
    --checksum=sha256:bb1211dac59ef4c54b7a8ad4755a913d36d2e81b34ca1d4cb9ffa9d5633df01f \
    https://repo1.maven.org/maven2/org/mariadb/jdbc/mariadb-java-client/4.0.0/mariadb-java-client-4.0.0.jar \
    /usr/share/logstash/drivers/mariadb-java-client.jar

COPY --chown=logstash:root config/ /usr/share/logstash/config/
COPY --chown=logstash:root pipeline/ /usr/share/logstash/pipeline/
COPY --chown=logstash:root sql/ /usr/share/logstash/sql/
COPY --chown=logstash:root templates/ /usr/share/logstash/templates/
