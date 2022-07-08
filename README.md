# Heap-Diff
Script to compare heap dumps and detect anomalies of increase in memory usage
Docker run command:
```
docker run -d --name <Container_name> --mount type=bind,src=<Path where python script and heap dump is present>,target=/dump <Docker Image ID> \
/dump/multi.py \
<HPROF file path> \
<"0" for running without loading baseline and anything else for loading baseline> \
<ServerName (Stored in InfluxDB as bucket name> \
<Influx org name> \
<Slack incoming web-hook> \
<Dominator tree measurement name> \
<Histogram data measurement name> \
<Influx URL for connection> \
<"0" to exclude classes starting with "java" or "jdk" and anything else to include all classes> \
<Maximum heap size for MAT process (Usually slightly more than heapdump file size is preferable)> \
<How many number of days to consider for baseline retrieval>
```
