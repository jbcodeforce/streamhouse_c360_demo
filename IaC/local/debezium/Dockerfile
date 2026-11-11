# Debezium Connect worker + Confluent Avro converter (not shipped in the base image).
# Mirrors what start_debezium.sh does by downloading the converter into a cache dir
# and mounting it as a Connect plugin; here it is baked into the image instead.

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest AS avro
ARG AVRO_CONVERTER_VERSION=7.8.11
ARG AVRO_CONVERTER_SHA1=b6af8bff514ab11a5f13f5e5a445169c3bf1c7a8
RUN microdnf install -y unzip && microdnf clean all \
 && curl -fsSL --max-time 300 -o /tmp/avro.zip \
      "https://hub-downloads.confluent.io/api/plugins/confluentinc/kafka-connect-avro-converter/versions/${AVRO_CONVERTER_VERSION}/confluentinc-kafka-connect-avro-converter-${AVRO_CONVERTER_VERSION}.zip" \
 && echo "${AVRO_CONVERTER_SHA1}  /tmp/avro.zip" | sha1sum -c - \
 && unzip -q /tmp/avro.zip -d /tmp/avro \
 && mv "/tmp/avro/confluentinc-kafka-connect-avro-converter-${AVRO_CONVERTER_VERSION}/lib" /tmp/avro-lib

FROM quay.io/debezium/connect:3.0.0.Final
COPY --from=avro /tmp/avro-lib /kafka/connect/confluent-avro-converter
