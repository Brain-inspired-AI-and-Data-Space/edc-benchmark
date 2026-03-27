@echo off
cd /d E:\edc\Samples
start "" cmd /c java "-Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/consumer-configuration.properties" -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar
